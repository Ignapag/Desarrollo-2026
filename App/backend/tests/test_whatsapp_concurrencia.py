"""Carreras reales del bot con conexiones independientes y datos UUID propios."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import pytest_asyncio
from psycopg.conninfo import conninfo_to_dict

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.whatsapp.domain.mensajes import hash_referencia, referencia_en
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.presentation import procesamiento
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.soporte_bd import HOSTS_DESCARTABLES, conectar_o_omitir


@pytest_asyncio.fixture
async def conexiones_locales():
    # Estas pruebas confirman transacciones. La guarda no admite excepciones
    # remotas ni destinos implícitos del .env del equipo.
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("Concurrencia requiere DATABASE_URL explícita de una base local descartable")
    parametros = conninfo_to_dict(settings.database_url)
    if parametros.get("service") or os.environ.get("PGSERVICE"):
        pytest.skip("Concurrencia no admite servicios de conexión indirectos")
    for campo, variable in (("host", "PGHOST"), ("hostaddr", "PGHOSTADDR")):
        valor = parametros.get(campo) or os.environ.get(variable) or ""
        if any(destino not in HOSTS_DESCARTABLES for destino in valor.split(",") if destino):
            pytest.skip("Concurrencia solo escribe en PostgreSQL local descartable")
    conexiones = []
    try:
        for _ in range(2):
            conexiones.append(await conectar_o_omitir())
        yield conexiones
    finally:
        for conn in conexiones:
            await conn.rollback()
            await conn.close()


async def esperar_bloqueo_o_finalizacion(uow, tarea, pid):
    """Sin demoras fijas: espera la barrera de PostgreSQL o el fin de tx2.

    Si falta la serialización, tx2 puede terminar sin ver datos no confirmados
    de tx1. La aserción posterior sobre ENTREGADO detecta esa pérdida.
    """
    while not tarea.done():
        bloqueada = await uow.valor(
            "SELECT EXISTS (SELECT 1 FROM pg_locks "
            "WHERE pid=%s AND locktype='advisory' AND NOT granted)",
            (pid,),
        )
        if bloqueada:
            return
        # La consulta anterior ya cede al event loop mientras espera PostgreSQL.


@pytest.mark.parametrize("primera_operacion", ["resultado", "callback"])
async def test_entrega_no_se_pierde_con_transacciones_superpuestas(
    conexiones_locales,
    primera_operacion,
):
    conn1, conn2 = conexiones_locales
    assert conn1.info.backend_pid != conn2.info.backend_pid
    uow1, uow2 = UnidadDeTrabajo(conn1), UnidadDeTrabajo(conn2)
    sufijo = uuid4().hex
    clave = f"test-concurrencia:{sufijo}"
    proveedor_id = f"wamid.concurrencia.{sufijo}"
    telefono = "5492215550097"
    identificador = None
    tareas = []
    primera_preparada = asyncio.Event()
    permitir_commit = asyncio.Event()

    async def operar(uow, operacion):
        cola = ColaWhatsAppSQL(uow)
        if operacion == "resultado":
            await cola.resultado(identificador, "ACEPTADO", proveedor_id)
        else:
            await cola.estado_proveedor(proveedor_id, telefono, "delivered")

    async def primera():
        async with conn1.transaction():
            await operar(uow1, primera_operacion)
            # Todo el método, incluida reconciliación, terminó; sus escrituras
            # todavía no son visibles desde la otra conexión.
            primera_preparada.set()
            await permitir_commit.wait()

    async def segunda():
        async with conn2.transaction():
            await operar(uow2, "callback" if primera_operacion == "resultado" else "resultado")

    try:
        identificador = await uow1.valor(
            """INSERT INTO whatsapp_salida (clave,telefono,texto,estado,intentos)
            VALUES (%s,%s,'Prueba concurrente','ENVIANDO',1) RETURNING id""",
            (clave, telefono),
        )
        await conn1.commit()

        async with asyncio.timeout(10):
            tareas.append(asyncio.create_task(primera()))
            await primera_preparada.wait()
            tareas.append(asyncio.create_task(segunda()))
            await esperar_bloqueo_o_finalizacion(uow1, tareas[1], conn2.info.backend_pid)
            permitir_commit.set()
            await asyncio.gather(*tareas)

        fila = await uow1.uno(
            "SELECT estado,proveedor_id,intentos FROM whatsapp_salida WHERE id=%s AND clave=%s",
            (identificador, clave),
        )
        assert fila == {"estado": "ENTREGADO", "proveedor_id": proveedor_id, "intentos": 1}
        assert (
            await uow1.valor(
                "SELECT count(*) FROM whatsapp_estado_envio WHERE proveedor_id=%s AND telefono=%s",
                (proveedor_id, telefono),
            )
            == 1
        )
    finally:
        permitir_commit.set()
        for tarea in tareas:
            if not tarea.done():
                tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
        await conn1.rollback()
        await conn2.rollback()
        # No se limpia la cola, el seed ni los pedidos de la demostración.
        await uow1.ejecutar(
            "DELETE FROM whatsapp_estado_envio WHERE proveedor_id=%s AND telefono=%s",
            (proveedor_id, telefono),
        )
        await uow1.ejecutar(
            "DELETE FROM whatsapp_salida WHERE id=%s AND clave=%s",
            (identificador, clave),
        )
        await conn1.commit()


# --- Interpretación vinculada al contexto original -------------------------------


class InterpretadorEnPausa:
    """Retiene la interpretación, fuera de toda transacción, hasta que la prueba la libera."""

    def __init__(self, accion):
        self.accion = accion
        self.contextos = []
        self.interpretando = asyncio.Event()
        self.continuar = asyncio.Event()

    async def interpretar(self, texto, contexto):
        self.contextos.append(contexto)
        self.interpretando.set()
        await self.continuar.wait()
        return self.accion


@pytest_asyncio.fixture
async def worker_independiente(conexiones_locales, monkeypatch):
    """Cada etapa del worker abre su propia conexión y confirma como el pool real."""
    abiertas = []
    interpretador = InterpretadorEnPausa(
        {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate", "item_indice": 1}}
    )

    @asynccontextmanager
    async def conexion():
        conn = await conectar_o_omitir()
        abiertas.append(conn)
        try:
            yield conn
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    monkeypatch.setattr(procesamiento, "conexion", conexion)
    monkeypatch.setattr(procesamiento, "interpretador", lambda: interpretador)
    telefono = "54922" + str(uuid4().int)[:8]
    conn1, conn2 = conexiones_locales
    try:
        yield telefono, interpretador, abiertas, conn1, conn2
    finally:
        interpretador.continuar.set()
        await conn1.rollback()
        await conn2.rollback()
        # Solo se eliminan las filas del teléfono UUID de esta prueba.
        uow = UnidadDeTrabajo(conn1)
        pedidos = [
            fila["pedido_id"]
            for fila in await uow.todos(
                "SELECT pedido_id FROM whatsapp_borrador "
                "WHERE telefono=%s AND pedido_id IS NOT NULL",
                (telefono,),
            )
        ]
        await uow.ejecutar("DELETE FROM whatsapp_salida WHERE telefono=%s", (telefono,))
        await uow.ejecutar(
            "DELETE FROM whatsapp_atencion WHERE referencia_hash IN "
            "(SELECT referencia_hash FROM whatsapp_borrador WHERE telefono=%s)",
            (telefono,),
        )
        await uow.ejecutar("DELETE FROM whatsapp_cambio WHERE pedido_id = ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM whatsapp_entrada WHERE telefono=%s", (telefono,))
        await uow.ejecutar("DELETE FROM whatsapp_borrador WHERE telefono=%s", (telefono,))
        await uow.ejecutar("DELETE FROM movimiento_stock WHERE pedido_id = ANY(%s)", (pedidos,))
        await uow.ejecutar("DELETE FROM pedido WHERE id = ANY(%s)", (pedidos,))
        await conn1.commit()


async def borrador_listo(uow, telefono):
    cliente = await uow.valor("SELECT id FROM cliente ORDER BY id LIMIT 1")
    producto = await uow.uno(
        "SELECT p.id,p.variantes FROM producto p JOIN producto_ingrediente pi "
        "ON pi.producto_id=p.id JOIN ingrediente i ON i.id=pi.ingrediente_id "
        "WHERE p.activo AND lower(i.nombre)='tomate' ORDER BY p.id LIMIT 1"
    )
    variante = (producto["variantes"] or [{}])[0].get("nombre")
    return await construir_servicio(uow).crear_borrador(
        cliente,
        {
            "telefono": telefono,
            "tipo_entrega": "RETIRO",
            "metodo_pago": "EFECTIVO",
            "items": [{"producto_id": producto["id"], "cantidad": 1, "variante": variante}],
        },
    )


async def vincular(uow, telefono, identificador, mensaje):
    servicio = construir_servicio(uow)
    await servicio.recibir(identificador, telefono, mensaje)
    await servicio.procesar(identificador, {"accion": "consulta", "argumentos": {}})
    return await uow.valor(
        "SELECT pedido_id FROM whatsapp_borrador WHERE referencia_hash=%s",
        (hash_referencia(referencia_en(mensaje)),),
    )


async def test_interpretacion_tomada_sobre_a_no_modifica_b(worker_independiente):
    telefono, interpretador, abiertas, conn1, conn2 = worker_independiente
    uow1, uow2 = UnidadDeTrabajo(conn1), UnidadDeTrabajo(conn2)
    borrador_a = await borrador_listo(uow1, telefono)
    pedido_a = await vincular(uow1, telefono, f"{telefono}-a", borrador_a["mensaje"])
    borrador_b = await borrador_listo(uow1, telefono)
    await construir_servicio(uow1).recibir(f"{telefono}-cambio", telefono, "sin tomate")
    await conn1.commit()

    async with asyncio.timeout(15):
        tarea = asyncio.create_task(procesamiento.procesar_entrada(f"{telefono}-cambio"))
        await interpretador.interpretando.wait()
        # Gemini está "pensando" sin ninguna transacción del worker abierta.
        assert abiertas and all(conn.closed for conn in abiertas)
        async with conn2.transaction():
            await construir_servicio(uow2).pedidos.cambiar_estado(
                pedido_a, EstadoPedido.CANCELADO, usuario_id=None
            )
        async with conn2.transaction():
            pedido_b = await vincular(uow2, telefono, f"{telefono}-b", borrador_b["mensaje"])
        interpretador.continuar.set()
        await tarea

    assert [c["items"][0]["cantidad"] for c in interpretador.contextos] == [1]
    for pid in (pedido_a, pedido_b):
        assert (
            await uow1.valor("SELECT aclaraciones FROM pedido_item WHERE pedido_id=%s", (pid,))
            is None
        )
    entrada = await uow1.uno(
        "SELECT estado,respuesta,referencia_hash FROM whatsapp_entrada WHERE id=%s",
        (f"{telefono}-cambio",),
    )
    assert entrada["estado"] == "PROCESADO"
    assert "no apliqué" in entrada["respuesta"].lower()
    assert entrada["referencia_hash"] is None
    assert (
        await uow1.valor("SELECT count(*) FROM whatsapp_cambio WHERE pedido_id=%s", (pedido_b,))
        == 0
    )


async def test_contexto_desactualizado_del_mismo_pedido_se_reinterpreta(worker_independiente):
    telefono, interpretador, _, conn1, conn2 = worker_independiente
    uow1, uow2 = UnidadDeTrabajo(conn1), UnidadDeTrabajo(conn2)
    borrador_a = await borrador_listo(uow1, telefono)
    pedido_a = await vincular(uow1, telefono, f"{telefono}-a", borrador_a["mensaje"])
    await construir_servicio(uow1).recibir(f"{telefono}-cambio", telefono, "sin tomate")
    await conn1.commit()

    async with asyncio.timeout(15):
        tarea = asyncio.create_task(procesamiento.procesar_entrada(f"{telefono}-cambio"))
        await interpretador.interpretando.wait()
        # Otro mensaje del mismo pedido confirma una cantidad nueva y cambia su versión.
        async with conn2.transaction():
            servicio = construir_servicio(uow2)
            for sufijo, texto, accion in (
                ("doble", "cantidad 2", {"accion": "cantidad", "argumentos": {"cantidad": 2}}),
                ("ok", "confirmar", {"accion": "confirmar", "argumentos": {}}),
            ):
                await servicio.recibir(f"{telefono}-{sufijo}", telefono, texto)
                await servicio.procesar(f"{telefono}-{sufijo}", accion)
        interpretador.continuar.set()
        await tarea

    # La segunda interpretación usa el contexto vigente del mismo pedido.
    assert [c["items"][0]["cantidad"] for c in interpretador.contextos] == [1, 2]
    item = await uow1.uno(
        "SELECT cantidad,aclaraciones FROM pedido_item WHERE pedido_id=%s", (pedido_a,)
    )
    assert item == {"cantidad": 2, "aclaraciones": "Sin Tomate"}


@pytest.mark.parametrize(
    "misma_referencia,mismo_telefono", [(True, False), (True, True), (False, True)]
)
@pytest.mark.parametrize("inicio_legible", [False, True])
async def test_reclamo_publico_concurrente_es_unico(
    conexiones_locales, misma_referencia, mismo_telefono, inicio_legible
):
    """Compiten remitentes o borradores distintos, con tx1 todavía sin confirmar."""
    conn1, conn2 = conexiones_locales
    uow1, uow2 = UnidadDeTrabajo(conn1), UnidadDeTrabajo(conn2)
    sufijo = uuid4().hex
    telefono = f"549221{int(sufijo[:10], 16) % 10000000:07d}"
    otro = telefono if mismo_telefono else str(int(telefono) + 1)
    ids = [f"publico-carrera-{sufijo}-1", f"publico-carrera-{sufijo}-2"]
    referencias = []
    tarea = None
    try:
        producto = await uow1.uno("SELECT id,variantes FROM producto WHERE activo LIMIT 1")
        item = {"producto_id": producto["id"], "cantidad": 1,
                "variante": (producto["variantes"] or [{}])[0].get("nombre")}
        datos = {"items": [item], "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO"}
        if inicio_legible:
            datos["contacto"] = {"nombre": "Prueba", "apellido": "Carrera", "telefono": telefono}
        servicio = construir_servicio(uow1)
        a = await servicio.crear_borrador(None, datos)
        segunda_compra = {**datos, "items": [{**item, "cantidad": 2}]} if inicio_legible else datos
        b = a if misma_referencia else await servicio.crear_borrador(None, segunda_compra)
        referencias = list({hash_referencia(d["referencia"][3:]) for d in (a, b)})
        await servicio.recibir(ids[0], telefono, a["mensaje"])
        await servicio.recibir(ids[1], otro, b["mensaje"])
        await conn1.commit()

        # tx1 retiene la referencia y la identidad. tx2 debe esperar su commit.
        await servicio.procesar(ids[0], {"accion": "consulta"})

        async def segunda():
            async with conn2.transaction():
                return await construir_servicio(uow2).procesar(ids[1], {"accion": "consulta"})

        async with asyncio.timeout(10):
            tarea = asyncio.create_task(segunda())
            while not tarea.done():
                if await uow1.valor(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted)",
                    (conn2.info.backend_pid,),
                ):
                    break
            if not inicio_legible or mismo_telefono:
                assert not tarea.done(), "El segundo reclamo debe serializarse con el primero"
            await conn1.commit()
            respuesta = await tarea

        filas = await uow1.todos(
            "SELECT cliente_id,telefono,pedido_id FROM whatsapp_borrador "
            "WHERE referencia_hash=ANY(%s)", (referencias,),
        )
        assert len({f["cliente_id"] for f in filas}) == 1
        assert all(f["telefono"] == telefono and f["pedido_id"] for f in filas)
        assert len({f["pedido_id"] for f in filas}) == (1 if misma_referencia else 2)
        if not mismo_telefono:
            assert "resumen" in respuesta.lower()
            assert await uow1.valor(
                "SELECT id FROM cliente WHERE whatsapp_verificado=%s", (otro,)
            ) is None
    finally:
        if tarea and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await conn1.rollback()
        await conn2.rollback()
        filas = await uow1.todos(
            "SELECT pedido_id,cliente_id FROM whatsapp_borrador WHERE referencia_hash=ANY(%s)",
            (referencias,),
        )
        pedidos = [f["pedido_id"] for f in filas if f["pedido_id"]]
        clientes = [f["cliente_id"] for f in filas if f["cliente_id"]]
        await uow1.ejecutar(
            "DELETE FROM whatsapp_salida WHERE telefono=ANY(%s)", ([telefono, otro],)
        )
        await uow1.ejecutar("DELETE FROM whatsapp_entrada WHERE id=ANY(%s)", (ids,))
        await uow1.ejecutar(
            "DELETE FROM whatsapp_borrador WHERE referencia_hash=ANY(%s)", (referencias,)
        )
        await uow1.ejecutar("DELETE FROM pedido WHERE id=ANY(%s)", (pedidos,))
        await uow1.ejecutar(
            "DELETE FROM cliente WHERE id=ANY(%s) AND usuario_id IS NULL", (clientes,)
        )
        await conn1.commit()
