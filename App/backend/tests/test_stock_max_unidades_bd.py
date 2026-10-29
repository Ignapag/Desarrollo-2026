"""Unidades vendibles según stock y rechazo de cantidades que superan el stock."""

from decimal import Decimal

import pytest

from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.productos.infrastructure.repositorio_sql import RepositorioProductosSQL
from app.modules.stock.application.servicio_stock import StockInsuficiente
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_extras_bd import crear
from tests.test_productos_recetas import crear_producto_prueba
from tests.test_stock_consumo_bd import escenario


async def catalogo(uow, producto_id):
    productos = await RepositorioProductosSQL(uow).listar(solo_activos=True)
    return next(p for p in productos if p["id"] == producto_id)


@pytest.mark.parametrize(
    "saldo,maximo,disponible", [("3", 3, True), ("0", 0, False), ("1000", 50, True)]
)
async def test_catalogo_informa_unidades_que_alcanza_el_stock(uow, saldo, maximo, disponible):
    _, producto, _ = await escenario(uow, saldo=Decimal(saldo))
    fila = await catalogo(uow, producto)
    assert fila["max_unidades"] == maximo
    assert fila["disponible"] is disponible


async def test_catalogo_calcula_unidades_por_variante(uow):
    # 0,5 kg de stock: la Simple usa 0,125 (4 unidades) y la Doble 0,750 (ninguna).
    _, creado, _ = await crear_producto_prueba(uow)
    fila = await catalogo(uow, creado["id"])
    assert [v["max_unidades"] for v in fila["variantes"]] == [4, 0]
    assert fila["max_unidades"] == 4


async def test_pedido_sin_extras_no_supera_el_stock(uow):
    cliente, producto, _ = await escenario(uow, saldo=Decimal("2"))
    with pytest.raises(StockInsuficiente):
        await crear(uow, cliente, [ItemNuevoPedido(producto, 3)])
    # Dos líneas del mismo producto suman su demanda.
    with pytest.raises(StockInsuficiente):
        await crear(uow, cliente, [ItemNuevoPedido(producto, 2), ItemNuevoPedido(producto, 1)])
    pedido = await crear(uow, cliente, [ItemNuevoPedido(producto, 2)])
    assert pedido["items"][0]["cantidad"] == 2


async def test_carrito_web_no_supera_el_stock(uow):
    cliente, producto, _ = await escenario(uow, saldo=Decimal("1"))
    servicio = construir_servicio(uow)
    datos = {"telefono": "5492210000000", "tipo_entrega": "RETIRO", "metodo_pago": "EFECTIVO"}
    with pytest.raises(StockInsuficiente):
        await servicio.crear_borrador(
            cliente, {**datos, "items": [{"producto_id": producto, "cantidad": 2}]}
        )
    borrador = await servicio.crear_borrador(
        cliente, {**datos, "items": [{"producto_id": producto, "cantidad": 1}]}
    )
    assert borrador["referencia"]
