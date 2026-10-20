"""Cola real sobre PostgreSQL descartable y frontera transaccional del worker."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.errores import ReglaDeNegocio
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.infrastructure.proveedores import ErrorEnvioIncierto
from app.modules.whatsapp.presentation import procesamiento

TELEFONO = "5492215550098"


async def crear_salida(uow, estado="PENDIENTE", intentos=0, proveedor_id=None):
    return await uow.valor(
        """INSERT INTO whatsapp_salida (clave,telefono,texto,estado,intentos,proveedor_id)
        VALUES (%s,%s,'Mensaje de prueba',%s,%s,%s) RETURNING id""",
        (f"test-cola:{uuid4().hex}", TELEFONO, estado, intentos, proveedor_id),
    )


async def salida(uow, identificador):
    return await uow.uno("SELECT * FROM whatsapp_salida WHERE id=%s", (identificador,))


@pytest.mark.parametrize("evento", ["delivered", "read"])
async def test_callback_antes_de_respuesta_se_conserva_y_eventos_tardios_no_degradan(uow, evento):
    cola = ColaWhatsAppSQL(uow)
    identificador = await crear_salida(uow)
    proveedor_id = f"wamid.{uuid4().hex}"
    reclamado = await cola.reclamar()
    assert reclamado["id"] == identificador

    # Meta puede notificar entrega mientras la llamada HTTP de envío aún no terminó.
    await cola.estado_proveedor(proveedor_id, TELEFONO, evento)
    await cola.resultado(identificador, "ACEPTADO", proveedor_id)
    assert (await salida(uow, identificador))["estado"] == "ENTREGADO"

    for tardio in (evento, "sent", "failed", "delivered", "read", "failed"):
        await cola.estado_proveedor(proveedor_id, TELEFONO, tardio)
        assert (await salida(uow, identificador))["estado"] == "ENTREGADO"
    # Repetir también el registro del resultado HTTP no reemplaza una entrega.
    await cola.resultado(identificador, "ACEPTADO", proveedor_id)
    assert (await salida(uow, identificador))["estado"] == "ENTREGADO"


async def test_callback_adelantado_de_fallo_agota_reintentos_automaticos(uow):
    cola = ColaWhatsAppSQL(uow)
    identificador = await crear_salida(uow)
    proveedor_id = f"wamid.{uuid4().hex}"
    await cola.reclamar()
    await cola.estado_proveedor(proveedor_id, TELEFONO, "failed")
    await cola.resultado(identificador, "ACEPTADO", proveedor_id)
    fila = await salida(uow, identificador)
    assert fila["estado"] == "FALLIDO"
    assert fila["intentos"] == 3
    assert await cola.reclamar() is None


async def test_callback_no_se_aplica_a_otro_destinatario(uow):
    cola = ColaWhatsAppSQL(uow)
    identificador = await crear_salida(uow)
    proveedor_id = f"wamid.{uuid4().hex}"
    await cola.reclamar()
    await cola.estado_proveedor(proveedor_id, "5492215559998", "delivered")
    await cola.resultado(identificador, "ACEPTADO", proveedor_id)
    assert (await salida(uow, identificador))["estado"] == "ACEPTADO"
    await cola.estado_proveedor(proveedor_id, TELEFONO, "delivered")
    assert (await salida(uow, identificador))["estado"] == "ENTREGADO"


async def test_dos_reclamos_solo_obtienen_una_vez_el_mismo_mensaje(uow):
    identificador = await crear_salida(uow)
    cola = ColaWhatsAppSQL(uow)
    reclamos = await asyncio.gather(cola.reclamar(), cola.reclamar())
    encontrados = [fila for fila in reclamos if fila]
    assert [fila["id"] for fila in encontrados] == [identificador]
    assert (await salida(uow, identificador))["intentos"] == 1


async def test_envio_abandonado_queda_incierto_y_nunca_se_reclama_para_reenviar(uow):
    identificador = await crear_salida(uow, estado="ENVIANDO", intentos=1)
    await uow.ejecutar(
        "UPDATE whatsapp_salida SET actualizado_en=now()-interval '6 minutes' WHERE id=%s",
        (identificador,),
    )
    cola = ColaWhatsAppSQL(uow)
    assert await cola.reclamar() is None
    fila = await salida(uow, identificador)
    assert fila["estado"] == "INCIERTO"
    assert fila["intentos"] == 1
    assert await cola.reclamar() is None


async def test_fallo_usa_backoff_y_se_agota_tras_tres_intentos(uow):
    identificador = await crear_salida(uow)
    cola = ColaWhatsAppSQL(uow)
    for intento, demora in ((1, 120), (2, 240), (3, 480)):
        reclamado = await cola.reclamar()
        assert reclamado["id"] == identificador
        assert reclamado["intentos"] == intento
        await cola.resultado(identificador, "FALLIDO")
        fila = await salida(uow, identificador)
        ahora = await uow.valor("SELECT now()")
        assert fila["proximo_intento_en"] - ahora == timedelta(seconds=demora)
        assert await cola.reclamar() is None
        await uow.ejecutar(
            "UPDATE whatsapp_salida SET proximo_intento_en=now()-interval '1 second' WHERE id=%s",
            (identificador,),
        )
    assert await cola.reclamar() is None
    assert (await salida(uow, identificador))["intentos"] == 3


async def test_envio_simulado_no_se_convierte_en_aceptado_o_entregado_real(uow):
    identificador = await crear_salida(uow)
    cola = ColaWhatsAppSQL(uow)
    await cola.reclamar()
    await cola.resultado(identificador, "SIMULADO", "sim-prueba")
    await cola.estado_proveedor("sim-prueba", TELEFONO, "delivered")
    fila = await salida(uow, identificador)
    assert fila["estado"] == "SIMULADO"
    assert await cola.reclamar() is None


async def test_ventana_solo_se_abre_con_entrada_del_destinatario_en_ultimas_24h(uow):
    cola = ColaWhatsAppSQL(uow)
    assert not await cola.dentro_ventana(TELEFONO)
    entrada_id = f"test-ventana:{uuid4().hex}"
    await uow.ejecutar(
        """INSERT INTO whatsapp_entrada(id,telefono,texto,creado_en)
        VALUES (%s,%s,'Prueba de ventana',now()-interval '24 hours')""",
        (entrada_id, TELEFONO),
    )
    assert not await cola.dentro_ventana(TELEFONO)
    await uow.ejecutar(
        "UPDATE whatsapp_entrada SET creado_en=now()-interval '23 hours' WHERE id=%s",
        (entrada_id,),
    )
    assert await cola.dentro_ventana(TELEFONO)
    assert not await cola.dentro_ventana("5492215559998")


@pytest.fixture
def worker_aislado(monkeypatch):
    """Doble de la frontera SQL: observa vida de transacción y resultado persistido."""
    observado = SimpleNamespace(
        abiertas=0,
        resultados=[],
        envios=[],
        ventana=True,
        modo="real",
        error=None,
        mensaje={"id": 7, "telefono": TELEFONO, "texto": "Pedido recibido"},
    )

    @asynccontextmanager
    async def conexion():
        observado.abiertas += 1
        try:
            yield object()
        finally:
            observado.abiertas -= 1

    class UowFalsa:
        def __init__(self, conn):
            self.conn = conn

        async def valor(self, sql, parametros=None):
            assert observado.abiertas == 1
            return False

        async def ejecutar(self, sql, parametros=None):
            assert observado.abiertas == 1
            return 1

    class ColaFalsa:
        def __init__(self, uow):
            self.uow = uow

        async def reclamar(self):
            assert observado.abiertas == 1
            return observado.mensaje

        async def dentro_ventana(self, telefono):
            assert observado.abiertas == 1
            return observado.ventana

        async def resultado(self, identificador, estado, proveedor_id=None):
            assert observado.abiertas == 1
            observado.resultados.append((identificador, estado, proveedor_id))

    class TransporteFalso:
        async def enviar(self, telefono, texto):
            observado.envios.append((telefono, texto, observado.abiertas))
            if observado.error:
                raise observado.error
            return "wamid.prueba" if observado.modo == "real" else "sim-prueba"

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    monkeypatch.setattr(procesamiento, "UnidadDeTrabajo", UowFalsa)
    monkeypatch.setattr(procesamiento, "ColaWhatsAppSQL", ColaFalsa)
    monkeypatch.setattr(procesamiento, "transporte", TransporteFalso)
    monkeypatch.setattr(procesamiento, "settings", observado)
    # Propiedad con el nombre de configuración que consume la producción.
    observado.whatsapp_modo = "real"
    return observado


@pytest.mark.parametrize(
    ("modo", "estado", "proveedor_id"),
    [
        ("real", "ACEPTADO", "wamid.prueba"),
        ("simulado", "SIMULADO", "sim-prueba"),
    ],
)
async def test_worker_cierra_transaccion_antes_de_transportar(
    worker_aislado, modo, estado, proveedor_id
):
    observado = worker_aislado
    observado.whatsapp_modo = observado.modo = modo
    assert await procesamiento.enviar_uno()
    assert observado.envios == [(TELEFONO, "Pedido recibido", 0)]
    assert observado.resultados == [(7, estado, proveedor_id)]
    assert observado.abiertas == 0


@pytest.mark.parametrize(
    ("error", "estado"),
    [
        (ErrorEnvioIncierto("Se agotó la espera"), "INCIERTO"),
        (ReglaDeNegocio("Rechazo explícito del proveedor"), "FALLIDO"),
    ],
)
async def test_worker_distingue_timeout_incierto_de_rechazo(worker_aislado, error, estado):
    observado = worker_aislado
    observado.error = error
    assert await procesamiento.enviar_uno()
    assert observado.envios == [(TELEFONO, "Pedido recibido", 0)]
    assert observado.resultados == [(7, estado, None)]
    assert observado.abiertas == 0


async def test_worker_no_envia_texto_real_fuera_de_ventana(worker_aislado):
    observado = worker_aislado
    observado.ventana = False
    assert await procesamiento.enviar_uno()
    assert observado.envios == []
    assert observado.resultados == [(7, "FALLIDO", None)]
    assert observado.abiertas == 0


async def test_worker_sin_mensaje_no_invoca_proveedor(worker_aislado):
    observado = worker_aislado
    observado.mensaje = None
    assert not await procesamiento.enviar_uno()
    assert observado.envios == []
    assert observado.resultados == []
    assert observado.abiertas == 0
