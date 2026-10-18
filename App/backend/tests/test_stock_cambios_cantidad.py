"""Ajustes diferenciales de stock por cantidades aprobadas por personal."""

from decimal import Decimal

import pytest
import pytest_asyncio

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.stock.application.servicio_stock import ServicioStock, StockInsuficiente
from app.modules.stock.domain.entidades import ItemConsumoStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL
from tests.test_stock_consumo_bd import crear_pedido, escenario


@pytest_asyncio.fixture
async def cambio(uow):
    cliente, producto, ingredientes = await escenario(
        uow, saldo=Decimal("10"), dos_ingredientes=True
    )
    await uow.ejecutar("UPDATE ingrediente SET nombre = 'tOmAtE' WHERE id = %s", (ingredientes[0],))
    pedido, item = await crear_pedido(uow, cliente, producto)
    await uow.ejecutar("UPDATE pedido_item SET cantidad = 2, subtotal = 200 WHERE id = %s", (item,))
    usuario_id = await uow.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente,))
    return ServicioStock(RepositorioStockSQL(uow)), pedido, item, producto, ingredientes, usuario_id


async def consumir(uow, cambio, estado="CONFIRMADO", omitidos=()):
    servicio, pedido, _, producto, _, _ = cambio
    await servicio.procesar_consumo(
        pedido, [ItemConsumoStock(producto, 2, ingredientes_omitidos=omitidos)]
    )
    await uow.ejecutar("UPDATE pedido SET estado = %s WHERE id = %s", (estado, pedido))


async def saldos(uow, ingredientes):
    return await uow.todos(
        "SELECT id, cantidad_actual FROM ingrediente " "WHERE id = ANY(%s) ORDER BY id",
        (ingredientes,),
    )


@pytest.mark.asyncio
async def test_aumento_solo_consume_diferencia_y_reintento_es_idempotente(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio)
    await servicio.ajustar_cantidad_item(pedido, item, 4, "cambio-1", usuario)
    await servicio.ajustar_cantidad_item(pedido, item, 4, "cambio-1", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [6, 6]
    assert (
        await uow.todos(
            "SELECT tipo, cantidad, usuario_id FROM movimiento_stock "
            "WHERE pedido_id = %s AND motivo = %s ORDER BY ingrediente_id",
            (pedido, "WHATSAPP_CANTIDAD:cambio-1"),
        )
        == [{"tipo": "CONSUMO", "cantidad": Decimal("2"), "usuario_id": usuario}] * 2
    )
    assert await uow.valor("SELECT cantidad FROM pedido_item WHERE id = %s", (item,)) == 2


@pytest.mark.asyncio
async def test_aumento_sin_stock_no_escribe_ningun_movimiento(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio)
    await uow.ejecutar(
        "UPDATE ingrediente SET cantidad_actual = 1 WHERE id = %s", (ingredientes[1],)
    )
    with pytest.raises(StockInsuficiente):
        async with uow.conn.transaction():
            await servicio.ajustar_cantidad_item(pedido, item, 4, "faltante", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 1]
    assert (
        await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s", (pedido,))
        == 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("estado", "saldo", "devoluciones"),
    [
        ("PENDIENTE", 9, 2),
        ("CONFIRMADO", 9, 2),
        ("EN_PREPARACION", 8, 0),
        ("LISTO", 8, 0),
        ("EN_CAMINO", 8, 0),
    ],
)
async def test_reduccion_devuelve_solo_antes_de_preparar(uow, cambio, estado, saldo, devoluciones):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio, estado)
    await servicio.ajustar_cantidad_item(pedido, item, 1, "reducir", usuario)
    await servicio.ajustar_cantidad_item(pedido, item, 1, "reducir", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [saldo, saldo]
    assert (
        await uow.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s " "AND tipo = 'DEVOLUCION'",
            (pedido,),
        )
        == devoluciones
    )


@pytest.mark.asyncio
async def test_sin_consumo_previo_no_ajusta_y_preparacion_usara_cantidad_vigente(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await servicio.ajustar_cantidad_item(pedido, item, 3, "sin-consumo", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [10, 10]
    assert (
        await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s", (pedido,))
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("nueva_cantidad", "saldo_segundo"), [(1, 9), (3, 7)])
async def test_cambio_respeta_ingredientes_omitidos_en_la_linea(
    uow, cambio, nueva_cantidad, saldo_segundo
):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await uow.ejecutar("UPDATE pedido_item SET aclaraciones = 'Sin Tomate' WHERE id = %s", (item,))
    await consumir(uow, cambio, omitidos=("tomate",))
    await servicio.ajustar_cantidad_item(pedido, item, nueva_cantidad, "sin-tomate", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [10, saldo_segundo]


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["ENTREGADO", "CANCELADO"])
async def test_pedido_cerrado_no_acepta_ajustes(uow, cambio, estado):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio, estado)
    with pytest.raises(ReglaDeNegocio):
        await servicio.ajustar_cantidad_item(pedido, item, 3, "cerrado", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]


@pytest.mark.asyncio
async def test_valida_entradas_y_pertenencia_del_item(uow, cambio):
    servicio, pedido, item, _, _, usuario = cambio
    for cantidad in (0, 51, True, 1.5):
        with pytest.raises(DatosInvalidos):
            await servicio.ajustar_cantidad_item(pedido, item, cantidad, "invalido", usuario)
    with pytest.raises(DatosInvalidos):
        await servicio.ajustar_cantidad_item(pedido, item, 3, "", usuario)
    with pytest.raises(NoEncontrado):
        await servicio.ajustar_cantidad_item(pedido, item + 1000000, 3, "item-ajeno", usuario)


@pytest.mark.asyncio
async def test_cambio_confirmado_antes_cocina_permite_ajuste_automatico(uow, cambio):
    servicio, pedido, item, _, ingredientes, _ = cambio
    await consumir(uow, cambio)
    await servicio.ajustar_cantidad_item(pedido, item, 3, "version:borrador:2", None)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [7, 7]


@pytest.mark.asyncio
@pytest.mark.parametrize("nueva_cantidad", [1, 3])
async def test_ajuste_en_cocina_requiere_aprobacion_de_personal(uow, cambio, nueva_cantidad):
    servicio, pedido, item, _, ingredientes, _ = cambio
    await consumir(uow, cambio, "EN_PREPARACION")
    with pytest.raises(ReglaDeNegocio):
        await servicio.ajustar_cantidad_item(pedido, item, nueva_cantidad, "sin-personal", None)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]


@pytest.mark.asyncio
async def test_reduccion_verifica_todo_el_neto_antes_de_devolver(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio)
    await uow.ejecutar(
        "INSERT INTO movimiento_stock (ingrediente_id,tipo,cantidad,saldo_resultante,pedido_id) "
        "VALUES (%s, 'DEVOLUCION', 2, 10, %s)",
        (ingredientes[1], pedido),
    )
    await uow.ejecutar(
        "UPDATE ingrediente SET cantidad_actual = 10 WHERE id = %s", (ingredientes[1],)
    )
    with pytest.raises(ReglaDeNegocio):
        await servicio.ajustar_cantidad_item(pedido, item, 1, "neto-insuficiente", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 10]
    assert (
        await uow.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s "
            "AND motivo = 'WHATSAPP_CANTIDAD:neto-insuficiente'",
            (pedido,),
        )
        == 0
    )


@pytest.mark.asyncio
async def test_error_despues_del_consumo_revierte_todo_el_ajuste(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio)
    consumir_real = servicio.repo.consumir

    async def consumir_y_fallar(*args, **kwargs):
        await consumir_real(*args, **kwargs)
        raise RuntimeError("fallo tras consumir diferencial")

    servicio.repo.consumir = consumir_y_fallar
    with pytest.raises(RuntimeError, match="fallo tras consumir"):
        async with uow.conn.transaction():
            await servicio.ajustar_cantidad_item(pedido, item, 3, "revertir", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]
    assert (
        await uow.valor("SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s", (pedido,))
        == 2
    )


@pytest.mark.asyncio
async def test_cambios_distintos_calculan_delta_desde_el_item_vigente(uow, cambio):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await consumir(uow, cambio)
    await servicio.ajustar_cantidad_item(pedido, item, 3, "primero", usuario)
    await uow.ejecutar("UPDATE pedido_item SET cantidad = 3, subtotal = 300 WHERE id = %s", (item,))
    await servicio.ajustar_cantidad_item(pedido, item, 1, "segundo", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [9, 9]


async def retroceder_cocina(uow, cambio, destino):
    _, pedido, _, _, _, usuario = cambio
    pedidos = obtener_servicio_pedidos(uow)
    await pedidos.cambiar_estado(pedido, EstadoPedido.EN_PREPARACION, usuario_id=usuario)
    await pedidos.cambiar_estado(
        pedido,
        destino,
        usuario_id=usuario,
        correccion=True,
        motivo="Captura de cocina equivocada",
        version_esperada=2,
        rol="EMPLEADO",
        tratamiento_stock="CONSERVAR",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("destino", [EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO])
async def test_reduccion_tras_retroceso_conserva_insumos_utilizados(uow, cambio, destino):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await retroceder_cocina(uow, cambio, destino)
    await servicio.ajustar_cantidad_item(pedido, item, 1, "reducir-tras-retroceso", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]
    assert (
        await uow.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s " "AND tipo='DEVOLUCION'",
            (pedido,),
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("destino", [EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO])
async def test_quitar_ingrediente_tras_retroceso_no_devuelve_stock(uow, cambio, destino):
    servicio, pedido, item, _, ingredientes, usuario = cambio
    await retroceder_cocina(uow, cambio, destino)
    with pytest.raises(ReglaDeNegocio, match="preparacion"):
        await servicio.devolver_ingrediente_antes_preparacion(pedido, item, "tomate", usuario)
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]


@pytest.mark.asyncio
@pytest.mark.parametrize("destino", [EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO])
@pytest.mark.parametrize("cantidad", [1, 3])
async def test_ajuste_automatico_tras_retroceso_requiere_personal(uow, cambio, destino, cantidad):
    servicio, pedido, item, _, ingredientes, _ = cambio
    await retroceder_cocina(uow, cambio, destino)
    with pytest.raises(ReglaDeNegocio, match="personal"):
        await servicio.ajustar_cantidad_item(
            pedido, item, cantidad, "sin-personal-tras-retroceso", None
        )
    assert [r["cantidad_actual"] for r in await saldos(uow, ingredientes)] == [8, 8]
