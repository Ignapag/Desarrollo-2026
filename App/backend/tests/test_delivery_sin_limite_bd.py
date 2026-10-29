"""Repartidores con carga acumulada, sin topes y entrega con cobro real."""

import asyncio
from uuid import uuid4

import pytest

from app.core.db import UnidadDeTrabajo
from app.errores import ReglaDeNegocio
from app.modules.delivery.presentation.dependencias import obtener_servicio_delivery
from tests.soporte_bd import conectar_o_omitir, mantenimiento_pruebas
from tests.test_delivery_bd import ENSENADA_CENTRO, crear_pedido_listo
from tests.test_delivery_seguridad import crear_repartidor


async def escenario(uow):
    servicio = obtener_servicio_delivery(uow)
    rider = await crear_repartidor(uow, uuid4().hex[:10])
    return servicio, rider


async def pedido(uow):
    return await crear_pedido_listo(uow, uuid4().hex[:10], ENSENADA_CENTRO)


@pytest.mark.asyncio
async def test_cinco_pedidos_se_asignan_al_mismo_repartidor_y_viaje(uow):
    servicio, rider = await escenario(uow)
    viajes = []
    for _ in range(5):
        resultado = await servicio.asignar_pedido(
            await pedido(uow), rider, motivo="Carga multiple", rol="EMPLEADO"
        )
        viajes.append(resultado["viaje_id"])
    assert len(set(viajes)) == 1
    assert await uow.valor("SELECT count(*) FROM envio WHERE viaje_id=%s", (viajes[0],)) == 5


@pytest.mark.asyncio
async def test_sql_no_impone_capacidad_de_dos_envios(uow):
    servicio, rider = await escenario(uow)
    viaje = await servicio.repo.crear_viaje(rider, asignado_por=None, automatica=False)
    for orden in range(1, 7):
        await servicio.repo.asignar_envio(
            pedido_id=await pedido(uow), viaje_id=viaje, zona_id=None,
            orden=orden, distancia_km=None,
        )
    assert await uow.valor("SELECT count(*) FROM envio WHERE viaje_id=%s", (viaje,)) == 6


@pytest.mark.asyncio
async def test_planificacion_ignora_el_tope_historico_y_no_agota_repartidor(uow):
    servicio, rider = await escenario(uow)
    await uow.ejecutar(
        "UPDATE repartidor SET estado='FUERA_DE_SERVICIO' WHERE usuario_id<>%s", (rider,)
    )
    await uow.ejecutar(
        "UPDATE parametro SET valor='1' WHERE clave='delivery.pedidos_por_viaje'"
    )
    ids = [await pedido(uow) for _ in range(6)]
    resultado = await servicio.planificar_y_asignar(rol="EMPLEADO")
    assert len(resultado.viajes) == 1
    assert set(resultado.viajes[0].pedidos) == set(ids)
    assert resultado.sin_asignar == []


@pytest.mark.asyncio
async def test_metadata_combo_se_conserva_al_renombrar_y_se_audita(uow):
    producto = await uow.valor("SELECT id FROM producto WHERE nombre='Combo: Típica + Bacon'")
    await uow.ejecutar(
        "UPDATE producto SET nombre='Combo renombrado',hamburguesas_por_unidad=3 WHERE id=%s",
        (producto,),
    )
    evento = await uow.uno(
        "SELECT datos FROM auditoria WHERE entidad='producto' AND entidad_id=%s "
        "ORDER BY id DESC LIMIT 1", (str(producto),),
    )
    assert evento["datos"]["antes"]["hamburguesas_por_unidad"] == 2
    assert evento["datos"]["despues"]["hamburguesas_por_unidad"] == 3


@pytest.mark.asyncio
async def test_carga_cuenta_hamburguesas_y_combos_no_medallones_ni_acompanamientos(uow):
    servicio, rider = await escenario(uow)
    pedido_id = await pedido(uow)
    for nombre, cantidad, retirado in [
        ("Cheese", 3, False), ("Combo: Típica + Bacon", 2, False),
        ("Combo: Nuggets + Papas", 7, False), ("Papas Fritas (Porción)", 10, False),
        ("Cheese", 99, True),
    ]:
        producto = await uow.valor("SELECT id FROM producto WHERE nombre=%s", (nombre,))
        await uow.ejecutar(
            "INSERT INTO pedido_item(pedido_id,producto_id,nombre_producto,cantidad,"
            "precio_unitario,subtotal,variante,eliminado_en) "
            "VALUES(%s,%s,%s,%s,1,%s,'Triple',CASE WHEN %s THEN now() END)",
            (pedido_id, producto, nombre, cantidad, cantidad, retirado),
        )
    await servicio.asignar_pedido(pedido_id, rider, motivo="Contar carga", rol="EMPLEADO")
    elegido = next(r for r in await servicio.repartidores_disponibles(rol="EMPLEADO")
                   if r["id"] == rider)
    assert elegido["hamburguesas_asignadas"] == 7


@pytest.mark.asyncio
async def test_un_viaje_en_ruta_permite_preparar_otro_y_cerrar_no_libera_antes(uow):
    servicio, rider = await escenario(uow)
    primero = await servicio.asignar_pedido(
        await pedido(uow), rider, motivo="Primero", rol="EMPLEADO"
    )
    await servicio.iniciar_viaje(primero["viaje_id"], rol="EMPLEADO")
    segundo = await servicio.asignar_pedido(
        await pedido(uow), rider, motivo="Siguiente", rol="EMPLEADO"
    )
    assert segundo["viaje_id"] != primero["viaje_id"]
    await servicio.iniciar_viaje(segundo["viaje_id"], rol="EMPLEADO")
    await servicio.registrar_entrega(primero["envio_id"], rol="EMPLEADO")
    assert await uow.valor(
        "SELECT estado FROM repartidor WHERE usuario_id=%s", (rider,)
    ) == "EN_RUTA"
    await servicio.registrar_entrega(segundo["envio_id"], rol="EMPLEADO")
    assert await uow.valor(
        "SELECT estado FROM repartidor WHERE usuario_id=%s", (rider,)
    ) == "DISPONIBLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("movimientos", [
    [], [(100, "COBRO", "PENDIENTE")], [(40, "COBRO", "CONCILIADO")],
    [(100, "COBRO", "CONCILIADO"), (20, "DEVOLUCION", "CONCILIADO")],
])
async def test_delivery_sin_cobrar_no_modifica_envio_ni_cierra_viaje(uow, movimientos):
    servicio, rider = await escenario(uow)
    pedido_id = await pedido(uow)
    await uow.ejecutar("UPDATE pedido SET subtotal=100,total=100 WHERE id=%s", (pedido_id,))
    asignado = await servicio.asignar_pedido(pedido_id, rider, motivo="Efectivo", rol="EMPLEADO")
    await servicio.iniciar_viaje(asignado["viaje_id"], rol="EMPLEADO")
    for monto, tipo, estado in movimientos:
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,monto,tipo,estado,metodo_pago) "
            "VALUES(%s,%s,%s,%s,'EFECTIVO')", (pedido_id, monto, tipo, estado),
        )
    with pytest.raises(ReglaDeNegocio, match="pago completo"):
        await servicio.registrar_entrega(asignado["envio_id"], rol="EMPLEADO")
    assert await uow.valor(
        "SELECT estado FROM envio WHERE pedido_id=%s", (pedido_id,)
    ) == "EN_CAMINO"
    assert await uow.valor(
        "SELECT estado FROM viaje WHERE id=%s", (asignado["viaje_id"],)
    ) == "EN_RUTA"


@pytest.mark.asyncio
@pytest.mark.parametrize("mismo_repartidor", [False, True])
async def test_asignaciones_concurrentes_bloquean_solo_el_repartidor_elegido(mismo_repartidor):
    primera, segunda = await conectar_o_omitir(), await conectar_o_omitir()
    a, b = UnidadDeTrabajo(primera), UnidadDeTrabajo(segunda)
    riders, pedidos, clientes, usuarios = [], [], [], []
    tarea = None
    try:
        riders = [await crear_repartidor(a, uuid4().hex[:10]) for _ in range(2)]
        pedidos = [await pedido(a) for _ in range(2)]
        for pedido_id in pedidos:
            cliente = await a.valor("SELECT cliente_id FROM pedido WHERE id=%s", (pedido_id,))
            clientes.append(cliente)
            usuarios.append(await a.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente,)))
        await primera.commit()
        original = await obtener_servicio_delivery(a).asignar_pedido(
            pedidos[0], riders[0], motivo="Primera asignacion", rol="EMPLEADO"
        )
        pid = await b.valor("SELECT pg_backend_pid()")
        tarea = asyncio.create_task(obtener_servicio_delivery(b).asignar_pedido(
            pedidos[1], riders[0] if mismo_repartidor else riders[1],
            motivo="Segunda asignacion", rol="EMPLEADO",
        ))
        if mismo_repartidor:
            async with asyncio.timeout(5):
                while not tarea.done() and not await a.valor(
                    "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND NOT granted)", (pid,)
                ):
                    await asyncio.sleep(0.01)
            assert not tarea.done(), "La segunda asignación debe esperar el lock del mismo rider"
            await primera.commit()
        siguiente = await asyncio.wait_for(tarea, timeout=5)
        await segunda.commit()
        if not mismo_repartidor:
            await primera.commit()
        assert (siguiente["viaje_id"] == original["viaje_id"]) is mismo_repartidor
        assert await a.valor("SELECT count(*) FROM envio WHERE pedido_id=ANY(%s)", (pedidos,)) == 2
    finally:
        if tarea and not tarea.done():
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        await segunda.rollback()
        await primera.rollback()
        async with mantenimiento_pruebas(a):
            await a.ejecutar("DELETE FROM viaje WHERE repartidor_id=ANY(%s)", (riders,))
            await a.ejecutar("DELETE FROM pedido WHERE id=ANY(%s)", (pedidos,))
            await a.ejecutar("DELETE FROM direccion WHERE cliente_id=ANY(%s)", (clientes,))
            await a.ejecutar("DELETE FROM cliente WHERE id=ANY(%s)", (clientes,))
            await a.ejecutar("DELETE FROM repartidor WHERE usuario_id=ANY(%s)", (riders,))
            await a.ejecutar("DELETE FROM usuario WHERE id=ANY(%s)", ([*riders, *usuarios],))
        await primera.commit()
        await segunda.close()
        await primera.close()
