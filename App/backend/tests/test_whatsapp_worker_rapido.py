"""Latencia y aislamiento del worker sin llamadas reales a proveedores."""

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.presentation import procesamiento
from scripts import whatsapp_worker


def preparar_worker(monkeypatch, entradas, interpretar):
    """Sustituye SQL/proveedor; conserva las etapas reales del procesamiento."""
    transaccion = ContextVar("transaccion", default=False)
    procesadas = []
    entradas_por_id = {entrada["id"]: entrada for entrada in entradas}

    @asynccontextmanager
    async def conexion():
        token = transaccion.set(True)
        try:
            yield object()
        finally:
            transaccion.reset(token)

    class Cola:
        def __init__(self, _):
            pass

        async def pendientes(self, limite=20, *, solo_demo=False):
            return [e for e in entradas if not solo_demo or e.get("demo")][:limite]

    class Servicio:
        async def preparar(self, identificador):
            assert transaccion.get()
            return {
                "texto": identificador,
                "contexto": {},
                "interpretar": True,
                "vinculo": {"telefono": entradas_por_id[identificador]["telefono"]},
            }

        async def procesar(self, identificador, accion, vinculo, *, reintentar):
            assert transaccion.get()
            procesadas.append(identificador)

    class Proveedor:
        async def interpretar(self, texto, contexto):
            # Cada tarea debe haber liberado SU conexión antes de esperar la red.
            assert not transaccion.get()
            await interpretar(texto)
            return {"accion": "consulta", "argumentos": {}}

    async def sin_salidas(*, solo_demo=False):
        return False

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    monkeypatch.setattr(procesamiento, "ColaWhatsAppSQL", Cola)
    monkeypatch.setattr(procesamiento, "construir_servicio", lambda _: Servicio())
    monkeypatch.setattr(procesamiento, "interpretador", lambda: Proveedor())
    monkeypatch.setattr(procesamiento, "enviar_uno", sin_salidas)
    monkeypatch.setattr(procesamiento, "settings", SimpleNamespace(chat_demo_gemini_modo=""))
    return procesadas


async def test_cliente_lento_no_bloquea_otro_y_su_segundo_mensaje_espera(monkeypatch):
    permitir_a = asyncio.Event()
    terminado_b = asyncio.Event()
    iniciadas = []

    async def interpretar(identificador):
        iniciadas.append(identificador)
        if identificador == "a1":
            await permitir_a.wait()
        if identificador == "b1":
            terminado_b.set()

    procesadas = preparar_worker(monkeypatch, [
        {"id": "a1", "telefono": "a"},
        {"id": "a2", "telefono": "a"},
        {"id": "b1", "telefono": "b"},
    ], interpretar)
    tarea = asyncio.create_task(procesamiento.procesar_lote())
    try:
        await asyncio.wait_for(terminado_b.wait(), timeout=1)
        assert "a2" not in iniciadas
        assert procesadas == ["b1"]
    finally:
        permitir_a.set()
        resultado = await tarea
    assert procesadas == ["b1", "a1", "a2"]
    assert resultado == {"entradas": 3}


async def test_a_lo_sumo_tres_conversaciones_interpretan_a_la_vez(monkeypatch):
    permitir = asyncio.Event()
    tres_activas = asyncio.Event()
    activas = 0
    maximo = 0

    async def interpretar(_):
        nonlocal activas, maximo
        activas += 1
        maximo = max(maximo, activas)
        if activas == 3:
            tres_activas.set()
        try:
            await permitir.wait()
        finally:
            activas -= 1

    procesadas = preparar_worker(monkeypatch, [
        {"id": str(i), "telefono": str(i)} for i in range(8)
    ], interpretar)
    tarea = asyncio.create_task(procesamiento.procesar_lote())
    try:
        await asyncio.wait_for(tres_activas.wait(), timeout=1)
        await asyncio.sleep(0)
        assert activas == 3
    finally:
        permitir.set()
        await tarea
    assert maximo == 3
    assert len(procesadas) == 8


async def test_fallo_de_una_conversacion_no_impide_las_otras_ni_la_salida(
    monkeypatch, caplog,
):
    intentos = []
    salidas = []

    async def interpretar(_):
        pass

    preparar_worker(monkeypatch, [
        {"id": "a1", "telefono": "a"},
        {"id": "a2", "telefono": "a"},
        {"id": "b1", "telefono": "b"},
    ], interpretar)

    async def procesar(identificador):
        intentos.append(identificador)
        if identificador == "a1":
            raise RuntimeError("contenido privado no debe aparecer")

    async def enviar(*, solo_demo=False):
        salidas.append(solo_demo)
        return False

    monkeypatch.setattr(procesamiento, "procesar_entrada", procesar)
    monkeypatch.setattr(procesamiento, "enviar_uno", enviar)
    await procesamiento.procesar_lote()
    assert intentos == ["a1", "b1"]
    assert salidas == [False]
    assert "RuntimeError" in caplog.text
    assert "contenido privado" not in caplog.text


async def test_cancelar_lote_cancela_proveedor_sin_procesar_el_siguiente(monkeypatch):
    iniciada = asyncio.Event()
    cancelada = asyncio.Event()

    async def interpretar(_):
        iniciada.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelada.set()

    procesadas = preparar_worker(monkeypatch, [
        {"id": "a1", "telefono": "a"},
        {"id": "a2", "telefono": "a"},
    ], interpretar)
    tarea = asyncio.create_task(procesamiento.procesar_lote())
    await asyncio.wait_for(iniciada.wait(), timeout=1)
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    assert cancelada.is_set()
    assert procesadas == []


async def test_solo_demo_no_interpreta_meta_ni_reclama_sus_salidas(monkeypatch):
    interpretadas = []
    salidas = []

    async def interpretar(identificador):
        interpretadas.append(identificador)

    preparar_worker(monkeypatch, [
        {"id": "meta1", "telefono": "meta"},
        {"id": "demo1", "telefono": "demo", "demo": True},
    ], interpretar)

    async def enviar(*, solo_demo=False):
        salidas.append(solo_demo)
        return False

    monkeypatch.setattr(procesamiento, "enviar_uno", enviar)
    resultado = await procesamiento.procesar_lote(solo_demo=True)
    assert interpretadas == ["demo1"]
    assert salidas == [True]
    assert resultado == {"entradas": 1}


async def test_cola_devuelve_telefono_y_solo_demo_filtra_en_sql(uow):
    sufijo = uuid4().hex
    telefono_demo = "000" + str(uuid4().int)[:12]
    telefono_meta = "549" + str(uuid4().int)[:12]
    cliente = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    await uow.ejecutar(
        "INSERT INTO chat_demo_sesion(token_hash,telefono,cliente_id) VALUES (%s,%s,%s)",
        (sufijo, telefono_demo, cliente),
    )
    for identificador, telefono in (("demo-" + sufijo, telefono_demo),
                                    ("meta-" + sufijo, telefono_meta)):
        await uow.ejecutar(
            "INSERT INTO whatsapp_entrada(id,telefono,texto) VALUES (%s,%s,'hola')",
            (identificador, telefono),
        )
    pendientes = await ColaWhatsAppSQL(uow).pendientes(10000, solo_demo=True)
    propias = [e for e in pendientes if e["id"].endswith(sufijo)]
    assert [(e["id"], e.get("telefono")) for e in propias] == [
        ("demo-" + sufijo, telefono_demo),
    ]


async def test_cola_preserva_recepcion_aunque_varias_entradas_compartan_fecha(uow):
    sufijo = uuid4().hex
    ids = ["orden-primero-" + sufijo, "orden-segundo-" + sufijo]
    for identificador in ids:
        await uow.ejecutar(
            "INSERT INTO whatsapp_entrada(id,telefono,texto) VALUES (%s,'5492215550000','hola')",
            (identificador,),
        )
    # now() coincide dentro del webhook transaccional; actualizar la fila no
    # autoriza a adelantar el siguiente mensaje por su posición física en la tabla.
    await uow.ejecutar("UPDATE whatsapp_entrada SET texto='hola de nuevo' WHERE id=%s", (ids[0],))
    pendientes = await ColaWhatsAppSQL(uow).pendientes(10000)
    assert [e["id"] for e in pendientes if e["id"] in ids] == ids


async def test_worker_drena_trabajo_con_pausa_corta_y_descansa_sin_trabajo(monkeypatch):
    pausas = []
    opciones = []
    resultados = iter([{"entradas": 3}, {"entradas": 0}, RuntimeError("privado")])

    async def lote(**kwargs):
        opciones.append(kwargs)
        resultado = next(resultados)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    async def pausar(segundos):
        pausas.append(segundos)
        if len(pausas) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(whatsapp_worker, "procesar_lote", lote)
    monkeypatch.setattr(whatsapp_worker, "pausar", pausar)
    with pytest.raises(asyncio.CancelledError):
        await whatsapp_worker.procesar_continuamente(solo_demo=True)
    assert 0 < pausas[0] <= 0.1
    assert pausas[1] >= 1
    assert pausas[2] >= 2
    assert opciones == [{"solo_demo": True}] * 3
