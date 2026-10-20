"""El canal demo queda aislado de Meta por identidad persistida, aun vencido."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.whatsapp.presentation import procesamiento


@pytest.fixture
def worker(uow, monkeypatch):
    observado = SimpleNamespace(abiertas=0, transacciones=0, envios=[])

    @asynccontextmanager
    async def conexion():
        observado.abiertas += 1
        observado.transacciones += 1
        try:
            yield uow.conn
        finally:
            observado.abiertas -= 1

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    return observado


async def encolar(uow, telefono):
    return await uow.valor(
        """INSERT INTO whatsapp_salida (clave,telefono,texto)
        VALUES (%s,%s,'Respuesta del bot') RETURNING id""",
        (f"test-demo-cola:{uuid4().hex}", telefono),
    )


@pytest.mark.parametrize("modo", ["real", "simulado"])
@pytest.mark.parametrize("vencida", [False, True])
async def test_destinatario_registrado_siempre_se_simula_sin_consultar_ventana(
    uow, monkeypatch, worker, modo, vencida
):
    telefono = "000221555000073"
    cliente = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    await uow.ejecutar(
        """INSERT INTO chat_demo_sesion (token_hash,telefono,cliente_id,expira_en)
        VALUES (%s,%s,%s,now()+make_interval(secs=>%s))""",
        (uuid4().hex, telefono, cliente, -3600 if vencida else 3600),
    )
    identificador = await encolar(uow, telefono)
    monkeypatch.setattr(
        procesamiento,
        "settings",
        SimpleNamespace(whatsapp_modo=modo, chat_demo_habilitado=False),
    )

    def transporte_prohibido():
        raise AssertionError("Una sesión demo nunca debe construir transporte")

    async def ventana_prohibida(self, telefono):
        raise AssertionError("Una sesión demo no depende de la ventana de Meta")

    monkeypatch.setattr(procesamiento, "transporte", transporte_prohibido)
    monkeypatch.setattr(procesamiento.ColaWhatsAppSQL, "dentro_ventana", ventana_prohibida)

    assert await procesamiento.enviar_uno()
    fila = await uow.uno("SELECT * FROM whatsapp_salida WHERE id=%s", (identificador,))
    assert fila["estado"] == "SIMULADO"
    assert fila["proveedor_id"] is None
    assert fila["intentos"] == 1
    assert worker.abiertas == 0
    assert worker.transacciones == 1
    assert not await procesamiento.enviar_uno()


@pytest.mark.parametrize("telefono", ["5492215550074", "000221555000074"])
async def test_destinatario_sin_sesion_conserva_transporte_fuera_de_transaccion(
    uow, monkeypatch, worker, telefono
):
    identificador = await encolar(uow, telefono)
    await uow.ejecutar(
        """INSERT INTO whatsapp_entrada (id,telefono,texto)
        VALUES (%s,%s,'Abrir ventana de prueba')""",
        (uuid4().hex, telefono),
    )
    monkeypatch.setattr(procesamiento, "settings", SimpleNamespace(whatsapp_modo="real"))

    class TransportePrueba:
        async def enviar(self, destinatario, texto):
            assert worker.abiertas == 0
            worker.envios.append((destinatario, texto))
            return "wamid.demo-control"

    monkeypatch.setattr(procesamiento, "transporte", TransportePrueba)

    assert await procesamiento.enviar_uno()
    fila = await uow.uno("SELECT * FROM whatsapp_salida WHERE id=%s", (identificador,))
    assert fila["estado"] == "ACEPTADO"
    assert fila["proveedor_id"] == "wamid.demo-control"
    assert worker.envios == [(telefono, "Respuesta del bot")]
    assert worker.abiertas == 0
    assert worker.transacciones == 2
