"""Calculo y validacion del consumo sin depender de PostgreSQL."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.application.servicio_stock import (
    PedidoYaProcesado,
    ServicioStock,
    StockInsuficiente,
)
from app.modules.stock.domain.entidades import ItemConsumoStock


class RepositorioFalso:
    def __init__(self):
        self.productos = {1: [(10, "1"), (20, "2")], 2: [(10, "1"), (30, "1")]}
        self.saldos = {10: Decimal("10"), 20: Decimal("10"), 30: Decimal("10")}
        self.nombres = {10: "Pan", 20: "Carne", 30: "Queso"}
        self.procesados = set()
        self.opciones = False
        self.movimientos = []
        self.bloqueos = []

    async def bloquear_pedido(self, pedido_id):
        return pedido_id == 7

    async def consumo_existente(self, pedido_id):
        return pedido_id in self.procesados

    async def pedido_tiene_opciones(self, pedido_id):
        return self.opciones

    async def recetas(self, producto_ids):
        return [
            {
                "producto_id": producto_id,
                "ingrediente_id": ingrediente_id,
                "cantidad_requerida": Decimal(cantidad),
            }
            for producto_id in producto_ids
            for ingrediente_id, cantidad in self.productos.get(producto_id, [])
        ] + [
            {"producto_id": producto_id, "ingrediente_id": None, "cantidad_requerida": None}
            for producto_id in producto_ids
            if producto_id in self.productos and not self.productos[producto_id]
        ]

    async def bloquear_ingredientes(self, ingrediente_ids):
        self.bloqueos = ingrediente_ids
        return [
            {"id": i, "nombre": self.nombres[i], "cantidad_actual": self.saldos[i]}
            for i in ingrediente_ids
        ]

    async def consumir(self, ingrediente_id, cantidad, pedido_id):
        self.saldos[ingrediente_id] -= cantidad
        movimiento = {
            "ingrediente_id": ingrediente_id,
            "cantidad": cantidad,
            "saldo_resultante": self.saldos[ingrediente_id],
            "pedido_id": pedido_id,
        }
        self.movimientos.append(movimiento)
        self.procesados.add(pedido_id)
        return movimiento


@pytest.fixture
def consumo():
    repo = RepositorioFalso()
    return ServicioStock(repo), repo


@pytest.mark.asyncio
async def test_consumo_simple_y_varios_ingredientes(consumo):
    servicio, repo = consumo
    movimientos = await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1)])
    assert [(m["ingrediente_id"], m["cantidad"]) for m in movimientos] == [
        (10, 1),
        (20, 2),
    ]
    assert repo.saldos[10] == 9
    assert repo.saldos[20] == 8


@pytest.mark.asyncio
async def test_agrupa_productos_repetidos_y_cantidad_mayor_que_uno(consumo):
    servicio, repo = consumo
    movimientos = await servicio.procesar_consumo(
        7, [ItemConsumoStock(1, 2), ItemConsumoStock(2, 1), ItemConsumoStock(1, 1)]
    )
    assert repo.bloqueos == [10, 20, 30]
    assert {m["ingrediente_id"]: m["cantidad"] for m in movimientos} == {
        10: 4,
        20: 6,
        30: 1,
    }
    assert len(repo.movimientos) == 3


@pytest.mark.asyncio
async def test_stock_exacto_es_valido(consumo):
    servicio, repo = consumo
    repo.saldos[10] = Decimal("1")
    repo.saldos[20] = Decimal("2")
    await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1)])
    assert repo.saldos[10] == repo.saldos[20] == 0


@pytest.mark.asyncio
async def test_faltantes_se_informan_antes_de_cualquier_escritura(consumo):
    servicio, repo = consumo
    repo.saldos[10] = Decimal("1")
    repo.saldos[20] = Decimal("1")
    with pytest.raises(StockInsuficiente) as error:
        await servicio.procesar_consumo(7, [ItemConsumoStock(1, 2)])
    assert error.value.detalles == {
        "ingredientes": [
            {
                "ingrediente_id": 10,
                "nombre": "Pan",
                "cantidad_requerida": Decimal("2"),
                "cantidad_disponible": Decimal("1"),
            },
            {
                "ingrediente_id": 20,
                "nombre": "Carne",
                "cantidad_requerida": Decimal("4"),
                "cantidad_disponible": Decimal("1"),
            },
        ]
    }
    assert repo.saldos[10] == repo.saldos[20] == 1
    assert repo.movimientos == []


@pytest.mark.asyncio
async def test_rechaza_opciones_informadas_o_persistidas(consumo):
    servicio, repo = consumo
    with pytest.raises(ReglaDeNegocio, match="personalizaciones"):
        await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1, ("extra",))])
    repo.opciones = True
    with pytest.raises(ReglaDeNegocio, match="personalizaciones"):
        await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1)])
    assert repo.movimientos == []


@pytest.mark.asyncio
async def test_rechaza_segundo_consumo(consumo):
    servicio, repo = consumo
    await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1)])
    with pytest.raises(PedidoYaProcesado):
        await servicio.procesar_consumo(7, [ItemConsumoStock(1, 1)])
    assert len(repo.movimientos) == 2


@pytest.mark.asyncio
async def test_valida_entradas_y_existencia(consumo):
    servicio, repo = consumo
    for pedido_id, items in (
        (0, [ItemConsumoStock(1, 1)]),
        (7, []),
        (7, [ItemConsumoStock(1, 0)]),
        (7, [ItemConsumoStock(0, 1)]),
    ):
        with pytest.raises(DatosInvalidos):
            await servicio.procesar_consumo(pedido_id, items)
    with pytest.raises(NoEncontrado, match="pedido"):
        await servicio.procesar_consumo(8, [ItemConsumoStock(1, 1)])
    with pytest.raises(NoEncontrado, match="productos"):
        await servicio.procesar_consumo(7, [ItemConsumoStock(99, 1)])
    repo.productos[3] = []
    with pytest.raises(ReglaDeNegocio, match="sin receta"):
        await servicio.procesar_consumo(7, [ItemConsumoStock(3, 1)])
