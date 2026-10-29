"""Precios, edición y movimientos de agregados sobre PostgreSQL descartable."""

import json
from decimal import Decimal

import pytest

from app.errores import DatosInvalidos
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.productos.application.servicio_productos import ServicioProductos
from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL
from app.modules.productos.presentation.esquemas import ProductoCrear, RecetaActualizar
from app.modules.stock.application.servicio_stock import StockInsuficiente
from tests.test_stock_consumo_bd import escenario


async def datos(uow):
    cliente, producto, (ingrediente,) = await escenario(uow, saldo=Decimal("20"))
    await uow.ejecutar(
        "INSERT INTO producto_opcion(producto_id,ingrediente_id,cantidad_requerida,"
        "costo_adicional,max_por_item) VALUES (%s,%s,0.5,300,3)",
        (producto, ingrediente),
    )
    return cliente, producto, ingrediente


async def crear(uow, cliente, items):
    return await obtener_servicio_pedidos(uow).crear(
        cliente_id=cliente,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=items,
    )


async def test_extras_congelados_cocina_reintentos_y_cancelacion(uow):
    cliente, producto, ingrediente = await datos(uow)
    pedido = await crear(
        uow,
        cliente,
        [
            ItemNuevoPedido(
                producto,
                2,
                extras=[{"ingrediente_id": ingrediente, "cantidad": 2}],
            )
        ],
    )
    item = pedido["items"][0]
    assert pedido["total"] == Decimal("1400")
    assert item["costo_opciones"] == Decimal("600")
    assert item["extras"][0]["cantidad_requerida"] == "0.500"
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    await servicio.stock.procesar(pedido["id"], await servicio.repo.items_para_stock(pedido["id"]))
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 16
    )
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.CANCELADO, usuario_id=None)
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 20
    )


async def test_configuraciones_distintas_y_precio_del_local(uow):
    cliente, producto, ingrediente = await datos(uow)
    pedido = await crear(
        uow,
        cliente,
        [
            ItemNuevoPedido(producto, 1),
            ItemNuevoPedido(
                producto,
                1,
                extras=[{"ingrediente_id": ingrediente, "cantidad": 1}],
            ),
        ],
    )
    assert len(pedido["items"]) == 2
    assert pedido["total"] == Decimal("500")
    catalogo = await RepositorioProductosSQL(uow).listar(solo_activos=True)
    extra = next(p for p in catalogo if p["id"] == producto)["extras_disponibles"][0]
    assert extra["precio"] == Decimal("300")
    assert extra["cantidad_requerida"] == Decimal("0.5")


async def test_rechaza_stock_conjunto_y_variante_manipulada(uow):
    cliente, producto, ingrediente = await datos(uow)
    await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=2 WHERE id=%s", (ingrediente,))
    with pytest.raises(StockInsuficiente):
        await crear(
            uow,
            cliente,
            [
                ItemNuevoPedido(producto, 1),
                ItemNuevoPedido(
                    producto,
                    1,
                    extras=[{"ingrediente_id": ingrediente, "cantidad": 1}],
                ),
            ],
        )
    with pytest.raises(DatosInvalidos):
        await crear(
            uow,
            cliente,
            [
                ItemNuevoPedido(
                    producto,
                    1,
                    variante="Doble",
                    extras=[{"ingrediente_id": ingrediente, "cantidad": 1}],
                )
            ],
        )


async def test_edicion_quita_extras_y_ajusta_precio_y_stock(uow):
    cliente, producto, ingrediente = await datos(uow)
    pedido = await crear(
        uow,
        cliente,
        [
            ItemNuevoPedido(
                producto,
                1,
                extras=[{"ingrediente_id": ingrediente, "cantidad": 2}],
            )
        ],
    )
    servicio = obtener_servicio_pedidos(uow)
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    pedido = await servicio.repo.detalle(pedido["id"])
    nuevo = await servicio.editar_items(
        pedido["id"],
        items=[{"id": pedido["items"][0]["id"], "cantidad": 1, "extras": []}],
        version_esperada=pedido["version"],
        usuario_id=None,
    )
    assert nuevo["total"] == Decimal("100")
    assert nuevo["items"][0]["extras"] == []
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (ingrediente,)) == 19
    )


async def test_dip_no_ofrece_extras_aunque_exista_configuracion(uow):
    _, producto, _ = await datos(uow)
    categoria = await uow.valor("SELECT id FROM categoria WHERE lower(nombre)='dips extra' LIMIT 1")
    await uow.ejecutar("UPDATE producto SET categoria_id=%s WHERE id=%s", (categoria, producto))
    assert await obtener_servicio_pedidos(uow).repo.extras_producto(producto, None) == []


async def test_variante_restringe_extras_a_receta_efectiva(uow):
    _, producto, ingrediente = await datos(uow)
    await uow.ejecutar(
        "UPDATE producto SET variantes=%s::jsonb WHERE id=%s",
        (
            json.dumps(
                [{"nombre": "Simple", "precio": 100}, {"nombre": "Especial", "precio": 200}]
            ),
            producto,
        ),
    )
    otro = await uow.valor(
        "INSERT INTO ingrediente(nombre,unidad_medida,cantidad_actual,umbral_minimo) "
        "VALUES (%s,'GR',100,1) RETURNING id",
        (f"Otra receta {producto}",),
    )
    await uow.ejecutar(
        "INSERT INTO producto_variante_ingrediente(producto_id,variante,ingrediente_id,"
        "cantidad_requerida) VALUES (%s,'Especial',%s,10)",
        (producto, otro),
    )
    servicio = obtener_servicio_pedidos(uow)
    with pytest.raises(DatosInvalidos):
        await servicio.cotizar_extras_item(
            {
                "producto_id": producto,
                "variante": "Especial",
                "extras": [{"ingrediente_id": ingrediente, "cantidad": 1}],
            }
        )


async def test_local_configura_venta_al_crear_y_editar_sin_modificar_costos(uow):
    _, producto, ingrediente = await datos(uow)
    categoria = await uow.valor("SELECT categoria_id FROM producto WHERE id=%s", (producto,))
    servicio = ServicioProductos(RepositorioProductosSQL(uow))
    costo = await uow.valor("SELECT costo_unitario FROM ingrediente WHERE id=%s", (ingrediente,))
    creado = await servicio.crear(
        ProductoCrear(
            categoria_id=categoria,
            nombre=f"Extra configurable {producto}",
            precio_base="100",
            ingredientes=[{"ingrediente_id": ingrediente, "cantidad_requerida": "1"}],
            extras=[
                {
                    "ingrediente_id": ingrediente,
                    "cantidad_requerida": "0.5",
                    "precio": "350",
                    "max_por_item": 2,
                }
            ],
        ).a_dominio()
    )
    receta = await servicio.obtener_receta(creado["id"])
    assert receta["extras"][0]["precio"] == Decimal("350")
    await servicio.actualizar_receta(
        creado["id"],
        RecetaActualizar(
            actualizado_en_esperado=receta["actualizado_en"],
            ingredientes=[{k: r[k] for k in ("ingrediente_id", "cantidad_requerida", "es_base")}
                          for r in receta["ingredientes"]],
            extras=[],
        ).a_dominio(),
    )
    assert (await servicio.obtener_receta(creado["id"]))["extras"] == []
    assert (
        await uow.valor("SELECT costo_unitario FROM ingrediente WHERE id=%s", (ingrediente,))
        == costo
    )


@pytest.mark.parametrize("desactivar", ["producto", "categoria"])
async def test_agregar_extras_requiere_producto_y_categoria_activos(uow, desactivar):
    cliente, producto, ingrediente = await datos(uow)
    pedido = await crear(uow, cliente, [ItemNuevoPedido(producto, 1)])
    if desactivar == "producto":
        await uow.ejecutar("UPDATE producto SET activo=FALSE WHERE id=%s", (producto,))
    else:
        await uow.ejecutar("UPDATE categoria SET activa=FALSE WHERE id="
                          "(SELECT categoria_id FROM producto WHERE id=%s)", (producto,))
    with pytest.raises(DatosInvalidos):
        await obtener_servicio_pedidos(uow).editar_items(
            pedido["id"], version_esperada=pedido["version"], items=[{
                "id": pedido["items"][0]["id"], "cantidad": 1,
                "extras": [{"ingrediente_id": ingrediente, "cantidad": 1}],
            }],
        )


@pytest.mark.parametrize("cantidad_extra,total", [(0, "100"), (1, "400")])
async def test_quitar_extras_de_producto_inactivo_sigue_permitido(uow, cantidad_extra, total):
    cliente, producto, ingrediente = await datos(uow)
    pedido = await crear(uow, cliente, [ItemNuevoPedido(
        producto, 1, extras=[{"ingrediente_id": ingrediente, "cantidad": 2}],
    )])
    await uow.ejecutar("UPDATE producto SET activo=FALSE WHERE id=%s", (producto,))
    nuevo = await obtener_servicio_pedidos(uow).editar_items(
        pedido["id"], version_esperada=pedido["version"], items=[{
            "id": pedido["items"][0]["id"], "cantidad": 1,
            "extras": [{"ingrediente_id": ingrediente, "cantidad": cantidad_extra}],
        }],
    )
    assert nuevo["total"] == Decimal(total)
