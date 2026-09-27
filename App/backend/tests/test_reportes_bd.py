"""Agregaciones reales en una transaccion reversible; requiere PostgreSQL local."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.reportes.infrastructure.repositorio_sql import RepositorioReportesSQL
from tests.test_delivery_bd import uow as uow  # fixture transaccional del proyecto


async def escenario(unidad):
    sufijo = uuid4().hex
    usuario_id = await unidad.valor(
        "INSERT INTO usuario (nombre, apellido, username, password_hash, rol) "
        "VALUES ('Reporte', 'Prueba', %s, 'x', 'CLIENTE') RETURNING id",
        (f"reportes_{sufijo}",),
    )
    await unidad.ejecutar(
        "INSERT INTO cliente (usuario_id, telefono_whatsapp) VALUES (%s, '5492210000000')",
        (usuario_id,),
    )
    categorias = []
    productos = []
    for numero in (1, 2):
        categoria_id = await unidad.valor(
            "INSERT INTO categoria (nombre) VALUES (%s) RETURNING id",
            (f"Categoria reporte {numero} {sufijo}",),
        )
        producto_id = await unidad.valor(
            "INSERT INTO producto (categoria_id, nombre, precio_base) "
            "VALUES (%s, %s, 100) RETURNING id",
            (categoria_id, f"Producto reporte {numero} {sufijo}"),
        )
        categorias.append(categoria_id)
        productos.append(producto_id)
    ingrediente_id = await unidad.valor(
        "INSERT INTO ingrediente (nombre, unidad_medida, umbral_minimo, costo_unitario) "
        "VALUES (%s, 'UNIDAD', 1, 20) RETURNING id",
        (f"Ingrediente reporte {sufijo}",),
    )
    await unidad.ejecutar(
        "INSERT INTO producto_ingrediente "
        "(producto_id, ingrediente_id, cantidad_requerida) VALUES (%s, %s, 1)",
        (productos[0], ingrediente_id),
    )
    return usuario_id, categorias, productos


async def pedido_con_item(unidad, cliente_id, producto_id, estado, fecha, *, cantidad=1):
    pedido_id = await unidad.valor(
        "INSERT INTO pedido (cliente_id, tipo_entrega, estado, confirmado_en) "
        "VALUES (%s, 'RETIRO', %s, %s) RETURNING id",
        (cliente_id, estado, fecha),
    )
    await unidad.ejecutar(
        "INSERT INTO pedido_item "
        "(pedido_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, 'Producto historico', %s, 100, %s)",
        (pedido_id, producto_id, cantidad, Decimal("100") * cantidad),
    )
    return pedido_id


@pytest.mark.asyncio
async def test_estados_filtros_agrupaciones_y_rentabilidad(uow):  # noqa: F811
    cliente_id, categorias, productos = await escenario(uow)
    septiembre = datetime(2026, 9, 1, 15, tzinfo=UTC)
    siguiente_dia = datetime(2026, 9, 2, 15, tzinfo=UTC)
    octubre = datetime(2026, 10, 1, 15, tzinfo=UTC)
    for estado in (
        "PENDIENTE",
        "CANCELADO",
        "CONFIRMADO",
        "EN_PREPARACION",
        "LISTO",
        "EN_CAMINO",
        "ENTREGADO",
    ):
        await pedido_con_item(uow, cliente_id, productos[0], estado, septiembre)
    await pedido_con_item(uow, cliente_id, productos[0], "CONFIRMADO", siguiente_dia)
    await pedido_con_item(uow, cliente_id, productos[1], "ENTREGADO", octubre)

    repo = RepositorioReportesSQL(uow)
    dias = await repo.ventas(
        date(2026, 9, 1),
        date(2026, 9, 1),
        "day",
        None,
        productos[0],
        incluir_montos=True,
    )
    assert len(dias) == 1
    assert dias[0]["cantidad_vendida"] == 5
    assert dias[0]["cantidad_pedidos"] == 5
    assert dias[0]["monto_total"] == 500

    semana = await repo.ventas(
        date(2026, 9, 1),
        date(2026, 9, 30),
        "week",
        categorias[0],
        None,
        incluir_montos=False,
    )
    assert len(semana) == 1
    assert semana[0]["cantidad_vendida"] == 6
    assert "monto_total" not in semana[0]
    meses = await repo.ventas(
        date(2026, 9, 1),
        date(2026, 10, 31),
        "month",
        None,
        None,
        incluir_montos=True,
    )
    assert {(fila["periodo"], fila["producto_id"]) for fila in meses} == {
        (date(2026, 9, 1), productos[0]),
        (date(2026, 10, 1), productos[1]),
    }
    categoria_2 = await repo.ventas(
        date(2026, 9, 1),
        date(2026, 10, 31),
        "day",
        categorias[1],
        None,
        incluir_montos=False,
    )
    assert [fila["producto_id"] for fila in categoria_2] == [productos[1]]

    rentabilidad = await repo.rentabilidad(
        date(2026, 9, 1), date(2026, 9, 30), categorias[0], productos[0]
    )
    assert len(rentabilidad) == 1
    assert rentabilidad[0]["unidades_vendidas"] == 6
    assert rentabilidad[0]["ingreso_estimado"] == 600
    assert rentabilidad[0]["costo_estimado"] == 120


@pytest.mark.asyncio
async def test_ingreso_conciliado_devoluciones_y_propina(uow):  # noqa: F811
    cliente_id, _, productos = await escenario(uow)
    fecha = datetime(2026, 9, 1, 15, tzinfo=UTC)
    pedido_id = await pedido_con_item(uow, cliente_id, productos[0], "CONFIRMADO", fecha)
    await uow.ejecutar(
        "INSERT INTO pedido_item "
        "(pedido_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal) "
        "VALUES (%s, %s, 'Segundo item', 1, 100, 100)",
        (pedido_id, productos[1]),
    )
    for tipo, estado, monto, propina in (
        ("COBRO", "CONCILIADO", 100, 25),
        ("DEVOLUCION", "CONCILIADO", 30, 0),
        ("COBRO", "PENDIENTE", 50, 0),
        ("COBRO", "ANULADO", 60, 0),
    ):
        await uow.ejecutar(
            "INSERT INTO pago "
            "(pedido_id, tipo, metodo_pago, monto, propina, estado, conciliado_en) "
            "VALUES (%s, %s, 'EFECTIVO', %s, %s, %s, %s)",
            (pedido_id, tipo, monto, propina, estado, fecha),
        )
    repo = RepositorioReportesSQL(uow)
    pagos = await repo.pagos_por_metodo(date(2026, 9, 1), date(2026, 9, 1))
    assert pagos == [{"metodo_pago": "EFECTIVO", "ingreso_neto": Decimal("70")}]
    # Dos items y cuatro pagos del mismo pedido no multiplican importes.
    assert sum(fila["ingreso_neto"] for fila in pagos) == 70
