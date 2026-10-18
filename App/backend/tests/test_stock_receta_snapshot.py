"""Cantidades de variantes y fracciones fijadas en la compra, con PostgreSQL descartable."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio

from app.errores import ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido
from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL
from tests.test_stock_consumo_bd import escenario


@pytest_asyncio.fixture
async def receta(uow):
    cliente, producto, (pan, carne) = await escenario(
        uow, saldo=Decimal("10"), dos_ingredientes=True
    )
    tomate = await uow.valor(
        "INSERT INTO ingrediente(nombre,unidad_medida,cantidad_actual,umbral_minimo) "
        "VALUES ('tOmAtE','UNIDAD',10,1) RETURNING id"
    )
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente(producto_id,ingrediente_id,cantidad_requerida) "
        "VALUES (%s,%s,0.25)", (producto, tomate),
    )
    await uow.ejecutar(
        "UPDATE producto SET variantes=%s::jsonb WHERE id=%s",
        (json.dumps([{"nombre": "Simple", "precio": 100}, {"nombre": "Doble", "precio": 150}]),
         producto),
    )
    for ingrediente, cantidad in ((pan, "1"), (carne, "2"), (tomate, "0.25")):
        await uow.ejecutar(
            "INSERT INTO producto_variante_ingrediente "
            "(producto_id,variante,ingrediente_id,cantidad_requerida) VALUES (%s,'Doble',%s,%s)",
            (producto, ingrediente, Decimal(cantidad)),
        )
    usuario = await uow.valor("SELECT usuario_id FROM cliente WHERE id=%s", (cliente,))
    return cliente, producto, pan, carne, tomate, usuario


async def crear(uow, receta, *, cantidad=3, aclaraciones=None):
    cliente, producto, *_ = receta
    return await obtener_servicio_pedidos(uow).crear(
        cliente_id=cliente, tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None,
        items=[ItemNuevoPedido(producto, cantidad, aclaraciones, "Doble")],
    )


async def saldos(uow, receta):
    return [await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id=%s", (i,))
            for i in receta[2:5]]


async def confirmar(uow, pedido):
    return await obtener_servicio_pedidos(uow).cambiar_estado(
        pedido["id"], EstadoPedido.CONFIRMADO, usuario_id=None,
    )


@pytest.mark.asyncio
async def test_variante_doble_y_cuarto_de_tomate_consumen_una_vez(uow, receta):
    pedido = await crear(uow, receta)
    item = await uow.uno("SELECT variante,receta_snapshot FROM pedido_item WHERE pedido_id=%s",
                         (pedido["id"],))
    assert item["variante"] == "Doble"
    assert {r["ingrediente_id"]: Decimal(r["cantidad_requerida"])
            for r in item["receta_snapshot"]} == {
                receta[2]: Decimal("1"), receta[3]: Decimal("2"), receta[4]: Decimal("0.25"),
            }
    await confirmar(uow, pedido)
    pedidos = obtener_servicio_pedidos(uow)
    await pedidos.cambiar_estado(pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=None)
    await pedidos.stock.procesar(pedido["id"], await pedidos.repo.items_para_stock(pedido["id"]))
    assert await saldos(uow, receta) == [Decimal("7"), Decimal("4"), Decimal("9.25")]
    assert await uow.valor(
        "SELECT count(*) FROM movimiento_stock WHERE pedido_id=%s AND tipo='CONSUMO'",
        (pedido["id"],),
    ) == 3


@pytest.mark.asyncio
async def test_mismo_producto_con_dos_variantes_conserva_cada_receta(uow, receta):
    pedido = await obtener_servicio_pedidos(uow).crear(
        cliente_id=receta[0], tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None,
        items=[ItemNuevoPedido(receta[1], 1, variante="Simple"),
               ItemNuevoPedido(receta[1], 1, variante="Doble")],
    )
    await confirmar(uow, pedido)
    assert await saldos(uow, receta) == [Decimal("8"), Decimal("7"), Decimal("9.5")]


@pytest.mark.asyncio
async def test_variante_legacy_sin_receta_explicita_conserva_base_sin_multiplicadores(uow, receta):
    await uow.ejecutar(
        "DELETE FROM producto_variante_ingrediente WHERE producto_id=%s", (receta[1],),
    )
    pedido = await crear(uow, receta, cantidad=1)
    await confirmar(uow, pedido)
    assert await saldos(uow, receta) == [Decimal("9"), Decimal("9"), Decimal("9.75")]


@pytest.mark.asyncio
async def test_disponibilidad_valida_la_variante_elegida(uow, receta):
    await uow.ejecutar("UPDATE ingrediente SET cantidad_actual=1 WHERE id=%s", (receta[3],))
    with pytest.raises(ReglaDeNegocio, match="sin stock"):
        await crear(uow, receta, cantidad=1)
    pedido = await obtener_servicio_pedidos(uow).crear(
        cliente_id=receta[0], tipo_entrega="RETIRO", direccion_id=None,
        direccion_nueva=None, observaciones=None,
        items=[ItemNuevoPedido(receta[1], 1, variante="Simple")],
    )
    await confirmar(uow, pedido)
    assert await saldos(uow, receta) == [Decimal("9"), Decimal("0"), Decimal("9.75")]


@pytest.mark.asyncio
async def test_backfill_infiere_variante_pero_conserva_receta_base_historica(uow, receta):
    pedido = await crear(uow, receta, cantidad=1)
    await uow.ejecutar(
        "UPDATE pedido_item SET variante=NULL,receta_snapshot=NULL WHERE pedido_id=%s",
        (pedido["id"],),
    )
    migracion = (Path(__file__).resolve().parents[2] / "db" / "migrations" /
                 "026_pedido_item_receta_snapshot.sql").read_text(encoding="utf-8")
    actualizaciones = migracion[
        migracion.index("UPDATE pedido_item item"):migracion.index("COMMENT ON COLUMN")
    ]
    await uow.ejecutar(actualizaciones)
    item = await uow.uno("SELECT variante,receta_snapshot FROM pedido_item WHERE pedido_id=%s",
                         (pedido["id"],))
    assert item["variante"] == "Doble"
    assert {r["ingrediente_id"]: Decimal(r["cantidad_requerida"])
            for r in item["receta_snapshot"]} == {
                receta[2]: Decimal("1"), receta[3]: Decimal("1"), receta[4]: Decimal("0.25"),
            }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nueva_cantidad", "saldos_esperados"),
    [(1, [Decimal("9"), Decimal("8"), Decimal("9.75")]),
     (3, [Decimal("7"), Decimal("4"), Decimal("9.25")])],
)
async def test_catalogo_editado_no_altera_consumo_ni_delta_del_pedido(
    uow, receta, nueva_cantidad, saldos_esperados,
):
    pedido = await crear(uow, receta, cantidad=2)
    await uow.ejecutar(
        "UPDATE producto_variante_ingrediente SET cantidad_requerida=7 WHERE producto_id=%s",
        (receta[1],),
    )
    await uow.ejecutar(
        "UPDATE producto_ingrediente SET cantidad_requerida=8 WHERE producto_id=%s",
        (receta[1],),
    )
    await confirmar(uow, pedido)
    servicio = ServicioStock(RepositorioStockSQL(uow))
    await servicio.ajustar_cantidad_item(pedido["id"], pedido["items"][0]["id"], nueva_cantidad,
                                       "snapshot-aumento", receta[5])
    await servicio.ajustar_cantidad_item(pedido["id"], pedido["items"][0]["id"], nueva_cantidad,
                                       "snapshot-aumento", receta[5])
    assert await saldos(uow, receta) == saldos_esperados


@pytest.mark.asyncio
async def test_omision_y_cancelacion_devuelven_solo_reserva_fraccionada(uow, receta):
    pedido = await crear(uow, receta, cantidad=3, aclaraciones="Sin Tomate")
    await confirmar(uow, pedido)
    assert await saldos(uow, receta) == [Decimal("7"), Decimal("4"), Decimal("10")]
    await obtener_servicio_pedidos(uow).cambiar_estado(
        pedido["id"], EstadoPedido.CANCELADO, usuario_id=None,
    )
    assert await saldos(uow, receta) == [Decimal("10"), Decimal("10"), Decimal("10")]
    servicio = ServicioStock(RepositorioStockSQL(uow))
    # El comando de reserva tiene guarda de estado: el ledger devuelve el neto exacto.
    assert await servicio.repo.consumo_neto_ingrediente(pedido["id"], receta[4]) == 0


@pytest.mark.asyncio
async def test_retiro_ingrediente_usa_snapshot_tras_editar_catalogo(uow, receta):
    pedido = await crear(uow, receta)
    await confirmar(uow, pedido)
    await uow.ejecutar(
        "UPDATE producto_variante_ingrediente SET cantidad_requerida=9 "
        "WHERE producto_id=%s AND ingrediente_id=%s", (receta[1], receta[4]),
    )
    servicio = ServicioStock(RepositorioStockSQL(uow))
    await servicio.devolver_ingrediente_antes_preparacion(
        pedido["id"], pedido["items"][0]["id"], "tomate", receta[5],
    )
    await servicio.devolver_ingrediente_antes_preparacion(
        pedido["id"], pedido["items"][0]["id"], "tomate", receta[5],
    )
    assert await saldos(uow, receta) == [Decimal("7"), Decimal("4"), Decimal("10")]


@pytest.mark.asyncio
async def test_reapertura_reconsume_snapshot_y_cancelacion_prev_cocina_devuelve_exactamente(
    uow, receta,
):
    pedido = await crear(uow, receta)
    await confirmar(uow, pedido)
    pedidos = obtener_servicio_pedidos(uow)
    cancelado = await pedidos.cambiar_estado(
        pedido["id"], EstadoPedido.CANCELADO, usuario_id=None,
    )
    assert await saldos(uow, receta) == [Decimal("10"), Decimal("10"), Decimal("10")]
    await uow.ejecutar(
        "DELETE FROM producto_variante_ingrediente WHERE producto_id=%s", (receta[1],),
    )
    await uow.ejecutar(
        "UPDATE producto_ingrediente SET cantidad_requerida=9 WHERE producto_id=%s", (receta[1],),
    )
    await pedidos.cambiar_estado(
        pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=receta[5],
        correccion=True, motivo="Nueva preparacion", rol="ADMINISTRADOR",
        version_esperada=cancelado["version"], tratamiento_stock="RECONSUMIR",
    )
    assert await saldos(uow, receta) == [Decimal("7"), Decimal("4"), Decimal("9.25")]
