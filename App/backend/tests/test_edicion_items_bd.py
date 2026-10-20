"""Edicion de composicion atomica con precios y recetas historicos."""

from decimal import Decimal

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.stock.application.servicio_stock import StockInsuficiente
from tests.test_stock_consumo_bd import escenario


async def crear(uow, *, saldo=Decimal("10")):
    cliente, producto, ingredientes = await escenario(uow, saldo=saldo)
    servicio = obtener_servicio_pedidos(uow)
    pedido = await servicio.crear(
        cliente_id=cliente,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(producto, 1)],
    )
    return servicio, pedido, producto, ingredientes[0]


@pytest.mark.asyncio
async def test_agregar_quitar_conserva_id_precio_receta_historial(uow):
    servicio, pedido, producto, _ = await crear(uow)
    original = pedido["items"][0]
    await uow.ejecutar("UPDATE producto SET precio_base=200 WHERE id=%s", (producto,))
    propuesta = [{"id": original["id"], "cantidad": 2}, {"producto_id": producto, "cantidad": 1}]
    cotizacion = await servicio.cotizar_items(pedido["id"], propuesta)
    assert cotizacion["total"] == 400
    editado = await servicio.editar_items(
        pedido["id"], items=propuesta, version_esperada=pedido["version"]
    )
    assert editado["version"] == pedido["version"] + 1
    assert editado["total"] == 400
    assert editado["items"][0]["id"] == original["id"]
    assert editado["items"][0]["precio_unitario"] == 100
    assert editado["items"][0]["receta_snapshot"] == original["receta_snapshot"]
    assert editado["historial"][-1]["cambios"]["items"]
    quitado = await servicio.editar_items(
        pedido["id"],
        items=[{"id": original["id"], "cantidad": 1}],
        version_esperada=editado["version"],
    )
    assert len(quitado["items"]) == 1
    assert quitado["items"][0]["id"] == original["id"]


@pytest.mark.asyncio
async def test_confirmado_ajusta_delta_sin_rechazar_reserva_propia(uow):
    servicio, pedido, producto, ingrediente = await crear(uow, saldo=Decimal("2"))
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    item = pedido["items"][0]
    resultado = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item["id"], "cantidad": 2}],
        version_esperada=pedido["version"] + 1,
    )
    assert resultado["total"] == 200
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 0
    )
    await servicio.cotizar_items(pedido["id"], [{"id": item["id"], "cantidad": 2}])
    with pytest.raises(StockInsuficiente):
        await servicio.cotizar_items(pedido["id"], [{"producto_id": producto, "cantidad": 3}])
    await servicio.editar_items(
        pedido["id"],
        items=[{"id": item["id"], "cantidad": 1}],
        version_esperada=resultado["version"],
    )
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cambio", ["vacio", "ajeno", "version", "cocina", "neto", "nota"])
async def test_rechaza_composicion_invalida_sin_modificar_pedido(uow, cambio):
    servicio, pedido, _, _ = await crear(uow)
    items = [{"id": pedido["items"][0]["id"], "cantidad": 1}]
    version = pedido["version"]
    if cambio == "vacio":
        items = []
    elif cambio == "ajeno":
        items[0]["id"] = 999999999
    elif cambio == "version":
        version = 8
    elif cambio == "cocina":
        await uow.ejecutar("UPDATE pedido SET preparacion_en=now() WHERE id=%s", (pedido["id"],))
    elif cambio == "neto":
        await uow.ejecutar(
            "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
            "VALUES (%s,'COBRO','EFECTIVO',200,'CONCILIADO')",
            (pedido["id"],),
        )
    elif cambio == "nota":
        items[0]["aclaraciones"] = "Sin carne"
    with pytest.raises((DatosInvalidos, ReglaDeNegocio)):
        await servicio.editar_items(pedido["id"], items=items, version_esperada=version)
    vigente = await servicio.detalle(pedido["id"])
    assert vigente["items"] == pedido["items"]
    assert vigente["version"] == pedido["version"]


@pytest.mark.asyncio
async def test_bacon_se_valida_y_restaurar_reconsume_snapshot(uow):
    cliente, producto, _ = await escenario(uow, saldo=Decimal("20"))
    panceta = await uow.valor("SELECT id FROM ingrediente WHERE lower(nombre)='panceta'")
    await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=50 WHERE id=%s", (panceta,))
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente(producto_id,ingrediente_id,cantidad_requerida) "
        "VALUES (%s,%s,2)",
        (producto, panceta),
    )
    servicio = obtener_servicio_pedidos(uow)
    pedido = await servicio.crear(
        cliente_id=cliente,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(producto, 1)],
    )
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    item_id = pedido["items"][0]["id"]
    sin = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item_id, "cantidad": 1, "aclaraciones": "sin bacon"}],
        version_esperada=pedido["version"],
    )
    assert sin["items"][0]["aclaraciones"] == "Sin Panceta"
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (panceta,)) == 50
    await uow.ejecutar(
        "UPDATE producto_ingrediente SET cantidad_requerida=10 WHERE producto_id=%s "
        "AND ingrediente_id=%s",
        (producto, panceta),
    )
    restaurado = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item_id, "cantidad": 1, "aclaraciones": None}],
        version_esperada=sin["version"],
    )
    assert restaurado["items"][0]["aclaraciones"] is None
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (panceta,)) == 48
    repetido = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item_id, "cantidad": 1, "aclaraciones": "Sin bacon"}],
        version_esperada=restaurado["version"],
    )
    assert repetido["version"] == restaurado["version"] + 1
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (panceta,)) == 50


@pytest.mark.asyncio
async def test_reemplazar_variante_usa_precio_actual_y_id_nuevo(uow):
    cliente, producto, _ = await escenario(uow, saldo=Decimal("20"))
    await uow.ejecutar(
        'UPDATE producto SET variantes=\'[{"nombre":"Simple","precio":100},'
        '{"nombre":"Doble","precio":180}]\'::jsonb WHERE id=%s',
        (producto,),
    )
    servicio = obtener_servicio_pedidos(uow)
    pedido = await servicio.crear(
        cliente_id=cliente,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(producto, 1, variante="Simple")],
    )
    with pytest.raises(DatosInvalidos):
        await servicio.cotizar_items(pedido["id"], [{"producto_id": producto, "cantidad": 1}])
    cambiado = await servicio.editar_items(
        pedido["id"],
        items=[{"producto_id": producto, "cantidad": 1, "variante": "Doble"}],
        version_esperada=pedido["version"],
    )
    assert cambiado["total"] == 180
    assert cambiado["items"][0]["variante"] == "Doble"
    assert cambiado["items"][0]["id"] != pedido["items"][0]["id"]


@pytest.mark.asyncio
async def test_reemplazar_producto_devuelve_y_consume_stock_en_un_solo_cambio(uow):
    servicio, pedido, _, ingrediente_original = await crear(uow)
    _, reemplazo, (ingrediente_nuevo,) = await escenario(uow, saldo=Decimal("5"))
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    cambiado = await servicio.editar_items(
        pedido["id"],
        items=[{"producto_id": reemplazo, "cantidad": 2}],
        version_esperada=pedido["version"],
    )
    assert cambiado["items"][0]["producto_id"] == reemplazo
    saldos = await uow.todos(
        "SELECT id,cantidad_actual FROM ingrediente WHERE id=ANY(%s)",
        ([ingrediente_original, ingrediente_nuevo],),
    )
    assert {fila["id"]: fila["cantidad_actual"] for fila in saldos} == {
        ingrediente_original: 10,
        ingrediente_nuevo: 3,
    }


@pytest.mark.asyncio
async def test_no_ignora_extras_y_no_aumenta_producto_desactivado(uow):
    servicio, pedido, producto, _ = await crear(uow)
    with pytest.raises(DatosInvalidos):
        await servicio.cotizar_items(
            pedido["id"], [{"producto_id": producto, "cantidad": 1, "extras": ["Carne"]}]
        )
    await uow.ejecutar("UPDATE producto SET activo=false WHERE id=%s", (producto,))
    with pytest.raises(ReglaDeNegocio):
        await servicio.cotizar_items(
            pedido["id"], [{"id": pedido["items"][0]["id"], "cantidad": 2}]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("precio_nuevo", [50, 150])
async def test_precio_cambiado_despues_de_cotizar_requiere_nueva_confirmacion(uow, precio_nuevo):
    servicio, pedido, producto, ingrediente = await crear(uow)
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    items = [{"producto_id": producto, "cantidad": 2}]
    cotizacion = await servicio.cotizar_items(pedido["id"], items)
    await uow.ejecutar("UPDATE producto SET precio_base=%s WHERE id=%s", (precio_nuevo, producto))
    with pytest.raises(ReglaDeNegocio, match="total"):
        await servicio.editar_items(
            pedido["id"],
            items=items,
            version_esperada=pedido["version"],
            total_esperado=cotizacion["total"],
        )
    vigente = await servicio.detalle(pedido["id"])
    assert vigente["items"] == pedido["items"]
    assert vigente["total"] == pedido["total"]
    assert vigente["version"] == pedido["version"]
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 9
    )
    nueva = await servicio.cotizar_items(pedido["id"], items)
    aplicado = await servicio.editar_items(
        pedido["id"],
        items=items,
        version_esperada=pedido["version"],
        total_esperado=nueva["total"],
    )
    assert aplicado["total"] == nueva["total"]


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmado", [False, True])
@pytest.mark.parametrize("reemplazar", [False, True])
async def test_no_agrega_producto_con_ingrediente_inactivo_aunque_tenga_saldo(
    uow, confirmado, reemplazar
):
    servicio, pedido, _, _ = await crear(uow)
    _, producto_nuevo, (ingrediente_nuevo,) = await escenario(uow, saldo=Decimal("20"))
    if confirmado:
        pedido = await servicio.cambiar_estado(
            pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None
        )
    await uow.ejecutar("UPDATE ingrediente SET activo=false WHERE id=%s", (ingrediente_nuevo,))
    items = [] if reemplazar else [{"id": pedido["items"][0]["id"], "cantidad": 1}]
    items.append({"producto_id": producto_nuevo, "cantidad": 1})
    with pytest.raises(ReglaDeNegocio, match="inactivo"):
        await servicio.cotizar_items(pedido["id"], items)
    with pytest.raises(ReglaDeNegocio, match="inactivo"):
        await servicio.editar_items(pedido["id"], items=items, version_esperada=pedido["version"])
    vigente = await servicio.detalle(pedido["id"])
    assert vigente["items"] == pedido["items"]
    assert vigente["version"] == pedido["version"]
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente_nuevo,))
        == 20
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmado", [False, True])
async def test_ingrediente_inactivo_rechaza_aumento_permite_reduccion_y_devolucion(uow, confirmado):
    servicio, pedido, _, ingrediente = await crear(uow)
    item_id = pedido["items"][0]["id"]
    pedido = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item_id, "cantidad": 2}],
        version_esperada=pedido["version"],
    )
    if confirmado:
        pedido = await servicio.cambiar_estado(
            pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None
        )
    await uow.ejecutar("UPDATE ingrediente SET activo=false WHERE id=%s", (ingrediente,))
    with pytest.raises(ReglaDeNegocio, match="inactivo"):
        await servicio.cotizar_items(pedido["id"], [{"id": item_id, "cantidad": 3}])
    reducido = await servicio.editar_items(
        pedido["id"],
        items=[{"id": item_id, "cantidad": 1}],
        version_esperada=pedido["version"],
    )
    assert reducido["items"][0]["cantidad"] == 1
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)
    ) == (9 if confirmado else 10)
