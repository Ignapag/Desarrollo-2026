"""Consumo SQL con fixture local: cada prueba revierte sus datos."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.db import UnidadDeTrabajo
from app.core.errores import ReglaDeNegocio
from app.modules.stock.application.servicio_stock import (
    PedidoYaProcesado,
    ServicioStock,
    StockInsuficiente,
)
from app.modules.stock.domain.entidades import ItemConsumoStock
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL


@pytest_asyncio.fixture
async def uow_consumo():
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL local no disponible: {exc.__class__.__name__}")
    try:
        yield UnidadDeTrabajo(conn)
    finally:
        await conn.rollback()
        await conn.close()


async def escenario(unidad, *, saldo=Decimal("2"), dos_ingredientes=False):
    sufijo = uuid4().hex
    usuario_id = await unidad.valor(
        "INSERT INTO usuario (nombre, apellido, username, password_hash, rol) "
        "VALUES ('Consumo', 'Prueba', %s, 'x', 'CLIENTE') RETURNING id",
        (f"consumo_{sufijo}",),
    )
    await unidad.ejecutar(
        "INSERT INTO cliente (usuario_id, telefono_whatsapp) VALUES (%s, '5492210000000')",
        (usuario_id,),
    )
    categoria_id = await unidad.valor(
        "INSERT INTO categoria (nombre) VALUES (%s) RETURNING id", (f"Consumo {sufijo}",)
    )
    producto_id = await unidad.valor(
        "INSERT INTO producto (categoria_id, nombre, precio_base) "
        "VALUES (%s, %s, 100) RETURNING id",
        (categoria_id, f"Producto consumo {sufijo}"),
    )
    ingredientes = []
    for numero in range(2 if dos_ingredientes else 1):
        ingrediente_id = await unidad.valor(
            "INSERT INTO ingrediente "
            "(nombre, unidad_medida, cantidad_actual, umbral_minimo) "
            "VALUES (%s, 'UNIDAD', %s, 1) RETURNING id",
            (f"Ingrediente consumo {numero} {sufijo}", saldo),
        )
        await unidad.ejecutar(
            "INSERT INTO producto_ingrediente "
            "(producto_id, ingrediente_id, cantidad_requerida) VALUES (%s, %s, 1)",
            (producto_id, ingrediente_id),
        )
        ingredientes.append(ingrediente_id)
    return usuario_id, producto_id, ingredientes


async def crear_pedido(unidad, cliente_id, producto_id):
    pedido_id = await unidad.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega) VALUES (%s, 'RETIRO') RETURNING id",
        (cliente_id,),
    )
    item_id = await unidad.valor(
        "INSERT INTO pedido_item "
        "(pedido_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, 'Producto', 1, 100, 100) RETURNING id",
        (pedido_id, producto_id),
    )
    return pedido_id, item_id


@pytest.mark.asyncio
async def test_descuenta_registra_alerta_y_cambia_disponibilidad(uow_consumo):
    unidad = uow_consumo
    cliente_id, producto_id, (ingrediente_id,) = await escenario(unidad)
    repo = RepositorioStockSQL(unidad)
    servicio = ServicioStock(repo)
    primero, _ = await crear_pedido(unidad, cliente_id, producto_id)
    segundo, _ = await crear_pedido(unidad, cliente_id, producto_id)

    movimiento = (await servicio.procesar_consumo(primero, [ItemConsumoStock(producto_id, 1)]))[0]
    assert movimiento["cantidad"] == 1
    assert movimiento["saldo_resultante"] == 1
    assert movimiento["pedido_id"] == primero
    assert await unidad.uno(
        "SELECT tipo, cantidad, saldo_resultante, pedido_id FROM movimiento_stock " "WHERE id = %s",
        (movimiento["movimiento_id"],),
    ) == {"tipo": "CONSUMO", "cantidad": 1, "saldo_resultante": 1, "pedido_id": primero}
    assert await unidad.uno(
        "SELECT nivel, estado FROM alerta_stock WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
        (ingrediente_id,),
    ) == {"nivel": "BAJO", "estado": "ACTIVA"}

    await servicio.procesar_consumo(segundo, [ItemConsumoStock(producto_id, 1)])
    assert (
        await unidad.valor(
            "SELECT cantidad_actual FROM ingrediente WHERE id = %s", (ingrediente_id,)
        )
        == 0
    )
    assert await unidad.uno(
        "SELECT nivel, cantidad_al_generar FROM alerta_stock "
        "WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
        (ingrediente_id,),
    ) == {"nivel": "AGOTADO", "cantidad_al_generar": 0}
    assert (
        await unidad.valor(
            "SELECT count(*) FROM alerta_stock WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
            (ingrediente_id,),
        )
        == 1
    )
    assert (
        await unidad.valor(
            "SELECT disponible FROM producto_disponible WHERE producto_id = %s", (producto_id,)
        )
        is False
    )
    with pytest.raises(PedidoYaProcesado):
        await servicio.procesar_consumo(primero, [ItemConsumoStock(producto_id, 1)])
    assert (
        await unidad.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s AND tipo = 'CONSUMO'",
            (primero,),
        )
        == 1
    )


@pytest.mark.asyncio
async def test_opciones_persistidas_se_rechazan_sin_escribir(uow_consumo):
    unidad = uow_consumo
    cliente_id, producto_id, (ingrediente_id,) = await escenario(unidad)
    pedido_id, item_id = await crear_pedido(unidad, cliente_id, producto_id)
    await unidad.ejecutar(
        "INSERT INTO pedido_item_opcion "
        "(pedido_item_id, ingrediente_id, nombre_opcion, tipo, cantidad) "
        "VALUES (%s, %s, 'Extra', 'AGREGADO', 1)",
        (item_id, ingrediente_id),
    )
    with pytest.raises(ReglaDeNegocio, match="personalizaciones"):
        await ServicioStock(RepositorioStockSQL(unidad)).procesar_consumo(
            pedido_id, [ItemConsumoStock(producto_id, 1)]
        )
    assert (
        await unidad.valor(
            "SELECT cantidad_actual FROM ingrediente WHERE id = %s", (ingrediente_id,)
        )
        == 2
    )
    assert (
        await unidad.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s", (pedido_id,)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_fallo_de_escritura_revierte_todo_el_consumo(uow_consumo):
    unidad = uow_consumo
    cliente_id, producto_id, ingredientes = await escenario(unidad, dos_ingredientes=True)
    pedido_id, _ = await crear_pedido(unidad, cliente_id, producto_id)
    repo = RepositorioStockSQL(unidad)
    consumir_real = repo.consumir
    llamadas = 0

    async def consumir_y_fallar(ingrediente_id, cantidad, pedido_id):
        nonlocal llamadas
        resultado = await consumir_real(ingrediente_id, cantidad, pedido_id)
        llamadas += 1
        if llamadas == 2:
            raise RuntimeError("fallo simulado despues de escribir")
        return resultado

    repo.consumir = consumir_y_fallar
    with pytest.raises(RuntimeError, match="fallo simulado"):
        async with unidad.conn.transaction():
            await ServicioStock(repo).procesar_consumo(
                pedido_id, [ItemConsumoStock(producto_id, 1)]
            )
    assert (
        await unidad.valor(
            "SELECT count(*) FROM ingrediente WHERE id = ANY(%s) AND cantidad_actual = 2",
            (ingredientes,),
        )
        == 2
    )
    assert (
        await unidad.valor(
            "SELECT count(*) FROM movimiento_stock WHERE pedido_id = %s", (pedido_id,)
        )
        == 0
    )
    assert (
        await unidad.valor(
            "SELECT count(*) FROM alerta_stock WHERE ingrediente_id = ANY(%s)",
            (ingredientes,),
        )
        == 0
    )


@pytest_asyncio.fixture
async def escenario_concurrente():
    """Datos propios confirmados para que dos conexiones puedan verlos; limpieza final."""
    try:
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"PostgreSQL local no disponible: {exc.__class__.__name__}")
    unidad = UnidadDeTrabajo(conn)
    try:
        async with conn.transaction():
            cliente_id, producto_id, (ingrediente_id,) = await escenario(unidad, saldo=Decimal("1"))
            pedido_a, item_a = await crear_pedido(unidad, cliente_id, producto_id)
            pedido_b, item_b = await crear_pedido(unidad, cliente_id, producto_id)
        yield producto_id, ingrediente_id, pedido_a, pedido_b
    finally:
        if "pedido_a" in locals():
            async with conn.transaction():
                categoria_id = await unidad.valor(
                    "SELECT categoria_id FROM producto WHERE id = %s", (producto_id,)
                )
                await unidad.ejecutar(
                    "DELETE FROM movimiento_stock WHERE pedido_id = ANY(%s)",
                    ([pedido_a, pedido_b],),
                )
                await unidad.ejecutar(
                    "DELETE FROM pedido_item WHERE id = ANY(%s)", ([item_a, item_b],)
                )
                await unidad.ejecutar(
                    "DELETE FROM pedido WHERE id = ANY(%s)", ([pedido_a, pedido_b],)
                )
                await unidad.ejecutar(
                    "DELETE FROM producto_ingrediente WHERE producto_id = %s", (producto_id,)
                )
                await unidad.ejecutar("DELETE FROM producto WHERE id = %s", (producto_id,))
                await unidad.ejecutar("DELETE FROM ingrediente WHERE id = %s", (ingrediente_id,))
                await unidad.ejecutar("DELETE FROM categoria WHERE id = %s", (categoria_id,))
                await unidad.ejecutar("DELETE FROM cliente WHERE usuario_id = %s", (cliente_id,))
                await unidad.ejecutar("DELETE FROM usuario WHERE id = %s", (cliente_id,))
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mismo_pedido", [False, True])
async def test_concurrencia_sin_sobregiro_ni_doble_consumo(escenario_concurrente, mismo_pedido):
    producto_id, ingrediente_id, pedido_a, pedido_b = escenario_concurrente

    async def intentar(pedido_id):
        conn = await psycopg.AsyncConnection.connect(
            settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
        )
        try:
            async with conn.transaction():
                await ServicioStock(RepositorioStockSQL(UnidadDeTrabajo(conn))).procesar_consumo(
                    pedido_id, [ItemConsumoStock(producto_id, 1)]
                )
            return "consumido"
        except (PedidoYaProcesado, StockInsuficiente) as exc:
            return type(exc).__name__
        finally:
            await conn.close()

    resultados = await asyncio.wait_for(
        asyncio.gather(intentar(pedido_a), intentar(pedido_a if mismo_pedido else pedido_b)),
        timeout=10,
    )
    assert resultados.count("consumido") == 1
    assert resultados.count("PedidoYaProcesado" if mismo_pedido else "StockInsuficiente") == 1
    conn = await psycopg.AsyncConnection.connect(
        settings.database_url, row_factory=psycopg.rows.dict_row, connect_timeout=2
    )
    try:
        unidad = UnidadDeTrabajo(conn)
        assert (
            await unidad.valor(
                "SELECT cantidad_actual FROM ingrediente WHERE id = %s", (ingrediente_id,)
            )
            == 0
        )
        assert (
            await unidad.valor(
                "SELECT count(*) FROM movimiento_stock "
                "WHERE pedido_id = ANY(%s) AND tipo = 'CONSUMO'",
                ([pedido_a, pedido_b],),
            )
            == 1
        )
    finally:
        await conn.close()
