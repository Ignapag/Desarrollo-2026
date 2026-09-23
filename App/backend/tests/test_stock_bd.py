"""Flujo SQL de stock en una transaccion que se revierte al terminar."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.domain.entidades import DatosIngrediente
from app.modules.stock.infrastructure.repositorio_sql import RepositorioStockSQL

pytest_plugins = ("tests.test_delivery_bd",)  # reutiliza su fixture transaccional


@pytest.mark.asyncio
async def test_alta_busqueda_reposiciones_historial_y_alertas(uow):
    repo = RepositorioStockSQL(uow)
    servicio = ServicioStock(repo)
    nombre = f"Insumo prueba {uuid4().hex}"

    creado = await servicio.registrar(
        DatosIngrediente(
            nombre=nombre,
            unidad_medida="UNIDAD",
            cantidad_actual=Decimal("0"),
            umbral_minimo=Decimal("5"),
        )
    )
    ingrediente_id = creado["id"]
    categoria_id = await uow.valor("SELECT id FROM categoria LIMIT 1")
    producto_id = await uow.valor(
        "INSERT INTO producto (categoria_id, nombre, precio_base) "
        "VALUES (%s, %s, 100) RETURNING id",
        (categoria_id, nombre),
    )
    await uow.ejecutar(
        "INSERT INTO producto_ingrediente "
        "(producto_id, ingrediente_id, cantidad_requerida, es_base) "
        "VALUES (%s, %s, 2, TRUE)",
        (producto_id, ingrediente_id),
    )
    assert (
        await uow.valor(
            "SELECT disponible FROM producto_disponible WHERE producto_id = %s", (producto_id,)
        )
        is False
    )
    encontrados = await servicio.listar(nombre=nombre, activo=True, nivel="SIN_STOCK")
    assert [fila["id"] for fila in encontrados] == [ingrediente_id]
    assert encontrados[0]["indicador_alerta"] is True
    alerta = await uow.uno(
        "SELECT nivel, estado FROM alerta_stock WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
        (ingrediente_id,),
    )
    assert alerta == {"nivel": "AGOTADO", "estado": "ACTIVA"}

    primera = await servicio.reponer(ingrediente_id, Decimal("2"), origen="PRUEBA")
    assert primera["saldo_anterior"] == 0
    assert primera["saldo_resultante"] == 2
    assert (
        await uow.valor(
            "SELECT disponible FROM producto_disponible WHERE producto_id = %s", (producto_id,)
        )
        is True
    )
    assert await uow.valor("SELECT activo FROM producto WHERE id = %s", (producto_id,)) is True
    alerta = await uow.uno(
        "SELECT nivel, cantidad_al_generar FROM alerta_stock "
        "WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
        (ingrediente_id,),
    )
    assert alerta == {"nivel": "BAJO", "cantidad_al_generar": Decimal("2")}

    movimientos = await servicio.historial(ingrediente_id=ingrediente_id, tipo="REPOSICION")
    assert len(movimientos) == 1
    assert movimientos[0]["saldo_anterior"] == 0
    assert movimientos[0]["cantidad"] == 2
    assert movimientos[0]["saldo_resultante"] == 2
    assert movimientos[0]["usuario_origen"] == "PRUEBA"
    assert movimientos[0]["pedido_id"] is None

    segunda = await servicio.reponer(ingrediente_id, Decimal("4"), origen="PRUEBA")
    assert segunda["saldo_anterior"] == 2
    assert segunda["saldo_resultante"] == 6
    assert (
        await uow.valor(
            "SELECT count(*) FROM alerta_stock " "WHERE ingrediente_id = %s AND estado = 'ACTIVA'",
            (ingrediente_id,),
        )
        == 0
    )
    assert (
        await uow.valor(
            "SELECT count(*) FROM alerta_stock "
            "WHERE ingrediente_id = %s AND estado = 'RESUELTA'",
            (ingrediente_id,),
        )
        == 1
    )
    assert (
        await uow.valor("SELECT cantidad_actual FROM ingrediente WHERE id = %s", (ingrediente_id,))
        == 6
    )


@pytest.mark.asyncio
async def test_modificar_no_cambia_saldo_y_busqueda_filtra_responsable(uow):
    repo = RepositorioStockSQL(uow)
    servicio = ServicioStock(repo)
    nombre = f"Insumo prueba {uuid4().hex}"
    responsable_id = await uow.valor("SELECT id FROM usuario WHERE estado = 'ACTIVO' LIMIT 1")
    creado = await servicio.registrar(
        DatosIngrediente(
            nombre=nombre,
            unidad_medida="KG",
            cantidad_actual=Decimal("10"),
            umbral_minimo=Decimal("2"),
            responsable_id=responsable_id,
        )
    )
    modificado = await servicio.modificar(creado["id"], {"umbral_minimo": Decimal("3")})
    assert modificado["cantidad_actual"] == 10
    assert modificado["umbral_minimo"] == 3
    encontrados = await servicio.listar(
        nombre=nombre, responsable_id=responsable_id, activo=True, nivel="NORMAL"
    )
    assert len(encontrados) == 1
