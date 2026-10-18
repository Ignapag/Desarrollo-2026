"""Regresiones de pedidos compartidas por web y WhatsApp."""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido, ServicioPedidos
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.infrastructure.repositorio_sql import RepositorioPedidosSQL
from app.modules.pedidos.infrastructure.stock import AdaptadorConsumoStock
from app.modules.stock.application.servicio_stock import (
    PedidoYaProcesado,
    ServicioStock,
    StockInsuficiente,
)
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL
from tests.test_stock_consumo_bd import escenario


class RepositorioPedidosMemoria:
    def __init__(self, estado="PENDIENTE", puede_preparar=True):
        self.pedido = {"id": 7, "estado": estado, "puede_preparar": puede_preparar}
        self.datos = None
        self.bloqueado = False

    async def cliente_valido(self, cliente_id):
        return cliente_id == 1

    async def productos(self, ids):
        return [{"id": i, "nombre": f"Producto {i}", "precio_base": Decimal("100"),
                 "disponible": True, "variantes": []} for i in ids]

    async def crear(self, **datos):
        self.datos = datos
        return {**self.pedido, **datos}

    async def obtener(self, pedido_id, *, bloquear=False):
        self.bloqueado = bloquear
        return self.pedido

    async def items_para_stock(self, pedido_id):
        return [{"producto_id": 1, "cantidad": 1, "aclaraciones": None}]

    async def cambiar_estado(self, pedido_id, estado, usuario_id):
        self.pedido["estado"] = estado.value
        return self.pedido


class StockMemoria:
    def __init__(self, error=None):
        self.error = error
        self.pedidos = []

    async def procesar(self, pedido_id, items):
        if self.error:
            raise self.error
        self.pedidos.append(pedido_id)

    async def procesar_consumo(self, pedido_id, items):
        await self.procesar(pedido_id, items)


class StockCaptura(StockMemoria):
    async def procesar_consumo(self, pedido_id, items):
        self.items = items


async def crear(servicio, items, **datos):
    return await servicio.crear(cliente_id=1, tipo_entrega="RETIRO", direccion_id=None,
                               direccion_nueva=None, observaciones=None, items=items, **datos)


@pytest.mark.asyncio
async def test_preserva_aclaraciones_distintas_y_agrupa_solo_lineas_iguales():
    repo = RepositorioPedidosMemoria()
    pedido = await crear(ServicioPedidos(repo, StockMemoria()), [
        ItemNuevoPedido(1, 1, "Sin Tomate"), ItemNuevoPedido(1, 2),
        ItemNuevoPedido(1, 3, "Sin Tomate"),
    ])
    assert [(i["cantidad"], i["aclaraciones"]) for i in pedido["items"]] == [
        (4, "Sin Tomate"), (2, None),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("items", [
    [ItemNuevoPedido(1, 51)],
    [ItemNuevoPedido(1, 30), ItemNuevoPedido(1, 21)],
    [ItemNuevoPedido(1, 30), ItemNuevoPedido(1, 21, "Sin Tomate")],
    [ItemNuevoPedido(i, 1) for i in range(1, 52)],
    [ItemNuevoPedido(1, True)],
])
async def test_rechaza_cantidades_o_lineas_excesivas_antes_de_persistir(items):
    repo = RepositorioPedidosMemoria()
    with pytest.raises(DatosInvalidos):
        await crear(ServicioPedidos(repo, StockMemoria()), items)
    assert repo.datos is None


@pytest.mark.asyncio
@pytest.mark.parametrize("canal", ["WEB", "WHATSAPP", "MOSTRADOR"])
async def test_crear_transmite_el_canal_validado(canal):
    pedido = await crear(ServicioPedidos(RepositorioPedidosMemoria(), StockMemoria()),
                         [ItemNuevoPedido(1, 1)], canal=canal)
    assert pedido["canal"] == canal


@pytest.mark.asyncio
async def test_crear_por_defecto_es_web_y_rechaza_canal_desconocido():
    servicio = ServicioPedidos(RepositorioPedidosMemoria(), StockMemoria())
    assert (await crear(servicio, [ItemNuevoPedido(1, 1)]))["canal"] == "WEB"
    with pytest.raises(DatosInvalidos):
        await crear(servicio, [ItemNuevoPedido(1, 1)], canal="OTRO")


@pytest.mark.asyncio
async def test_confirmado_sin_consumo_descuenta_antes_de_preparar():
    repo = RepositorioPedidosMemoria("CONFIRMADO")
    stock = StockMemoria()
    pedido = await ServicioPedidos(repo, stock).cambiar_estado(
        7, EstadoPedido.EN_PREPARACION, usuario_id=None)
    assert repo.bloqueado
    assert stock.pedidos == [7]
    assert pedido["estado"] == "EN_PREPARACION"


@pytest.mark.asyncio
async def test_transferencia_pendiente_no_prepara_ni_consume():
    repo = RepositorioPedidosMemoria("CONFIRMADO", puede_preparar=False)
    stock = StockMemoria()
    with pytest.raises(ReglaDeNegocio):
        await ServicioPedidos(repo, stock).cambiar_estado(
            7, EstadoPedido.EN_PREPARACION, usuario_id=None)
    assert repo.pedido["estado"] == "CONFIRMADO"
    assert stock.pedidos == []


@pytest.mark.asyncio
async def test_adaptador_tolera_consumo_previo_pero_propaga_falta_de_stock():
    items = [{"producto_id": 1, "cantidad": 1}]
    await AdaptadorConsumoStock(StockMemoria(PedidoYaProcesado("previo"))).procesar(7, items)
    with pytest.raises(StockInsuficiente):
        await AdaptadorConsumoStock(StockMemoria(StockInsuficiente("faltante"))).procesar(7, items)


@pytest.mark.asyncio
async def test_falta_stock_impide_cambio_de_estado():
    repo = RepositorioPedidosMemoria("CONFIRMADO")
    with pytest.raises(StockInsuficiente):
        await ServicioPedidos(repo, StockMemoria(StockInsuficiente("faltante"))).cambiar_estado(
            7, EstadoPedido.EN_PREPARACION, usuario_id=None)
    assert repo.pedido["estado"] == "CONFIRMADO"


@pytest.mark.asyncio
@pytest.mark.parametrize(("notas", "omitidos"), [
    ("Sin Tomate, Sin Lechuga", ("tomate", "lechuga")),
    ("Sin Tomate, cocinar bien", ()),
    ("Sin Carne", ()),
    (None, ()),
])
async def test_solo_notas_de_retiros_permitidos_afectan_consumo(notas, omitidos):
    stock = StockCaptura()
    await AdaptadorConsumoStock(stock).procesar(
        7, [{"producto_id": 1, "cantidad": 1, "aclaraciones": notas}])
    assert stock.items[0].ingredientes_omitidos == omitidos


@pytest.mark.asyncio
@pytest.mark.parametrize("canal", ["WEB", "WHATSAPP", "MOSTRADOR"])
async def test_sql_persiste_canal_y_aclaraciones_separadas(uow, canal):
    cliente_id, producto_id, _ = await escenario(uow)
    servicio = ServicioPedidos(RepositorioPedidosSQL(uow), StockMemoria())
    pedido = await servicio.crear(
        cliente_id=cliente_id, tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None, canal=canal,
        items=[ItemNuevoPedido(producto_id, 1, "Sin Tomate"), ItemNuevoPedido(producto_id, 2)],
    )
    assert await uow.valor("SELECT canal FROM pedido WHERE id = %s", (pedido["id"],)) == canal
    assert [(i["cantidad"], i["aclaraciones"]) for i in pedido["items"]] == [
        (1, "Sin Tomate"), (2, None),
    ]
    assert await RepositorioPedidosSQL(uow).items_para_stock(pedido["id"]) == [
        {"producto_id": producto_id, "cantidad": 1, "aclaraciones": "Sin Tomate"},
        {"producto_id": producto_id, "cantidad": 2, "aclaraciones": None},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("metodo", "estado_pago", "permitido"), [
    ("TRANSFERENCIA", "PENDIENTE", False),
    ("TRANSFERENCIA", "RECHAZADO", False),
    ("TRANSFERENCIA", "APROBADO", True),
    ("EFECTIVO", "PENDIENTE", True),
])
async def test_sql_solo_bloquea_transferencias_sin_aprobar(uow, metodo, estado_pago, permitido):
    cliente_id, producto_id, _ = await escenario(uow)
    repo = RepositorioPedidosSQL(uow)
    servicio = ServicioPedidos(repo, StockMemoria())
    pedido = await servicio.crear(
        cliente_id=cliente_id, tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None, items=[ItemNuevoPedido(producto_id, 1)],
    )
    assert (await repo.obtener(pedido["id"], bloquear=True))["puede_preparar"] is True
    await uow.ejecutar(
        "INSERT INTO whatsapp_borrador (referencia_hash, cliente_id, telefono, items, "
        "metodo_pago, estado_pago, pedido_id) VALUES (%s, %s, '5492215550000', '[]', %s, %s, %s)",
        (uuid4().hex, cliente_id, metodo, estado_pago, pedido["id"]),
    )
    await uow.ejecutar("UPDATE pedido SET metodo_pago_acordado=%s WHERE id=%s",
                       (metodo,pedido["id"]))
    if metodo == "TRANSFERENCIA" and estado_pago == "APROBADO":
        # La revisión acredita un pago conciliado por el importe observado.
        assert (await repo.obtener(pedido["id"], bloquear=True))["puede_preparar"] is False
        await uow.ejecutar(
            "INSERT INTO pago (pedido_id,metodo_pago,monto,estado) "
            "VALUES (%s,'TRANSFERENCIA',%s,'CONCILIADO')", (pedido["id"], pedido["total"]),
        )
    assert (await repo.obtener(pedido["id"], bloquear=True))["puede_preparar"] is permitido
    if permitido:
        actualizado = await servicio.cambiar_estado(
            pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=None)
        assert actualizado["estado"] == "EN_PREPARACION"
    else:
        with pytest.raises(ReglaDeNegocio):
            await servicio.cambiar_estado(
                pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=None)
        estado = await uow.valor("SELECT estado FROM pedido WHERE id = %s", (pedido["id"],))
        assert estado == "PENDIENTE"


@pytest.mark.asyncio
async def test_preparacion_sql_descuenta_receta_sin_ingrediente_retirado(uow):
    cliente_id, producto_id, (ingrediente_id,) = await escenario(uow)
    tomate = await uow.uno(
        "SELECT id, cantidad_actual FROM ingrediente WHERE lower(nombre) = 'tomate' LIMIT 1")
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente (producto_id, ingrediente_id, cantidad_requerida) "
        "VALUES (%s, %s, 1)", (producto_id, tomate["id"]),
    )
    servicio = ServicioPedidos(RepositorioPedidosSQL(uow), AdaptadorConsumoStock(
        ServicioStock(RepositorioStockSQL(uow))))
    pedido = await servicio.crear(
        cliente_id=cliente_id, tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None, canal="WHATSAPP",
        items=[ItemNuevoPedido(producto_id, 1, "Sin Tomate")],
    )
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None)
    await servicio.cambiar_estado(pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=None)
    movimientos = await uow.todos(
        "SELECT ingrediente_id, cantidad FROM movimiento_stock WHERE pedido_id = %s",
        (pedido["id"],),
    )
    assert movimientos == [{"ingrediente_id": ingrediente_id, "cantidad": Decimal("1")}]
    assert await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id = %s",
                           (tomate["id"],)) == tomate["cantidad_actual"]
