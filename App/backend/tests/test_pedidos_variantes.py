"""Precios y snapshots de variantes al crear pedidos."""

from decimal import Decimal

import pytest

from app.errores import DatosInvalidos
from app.modules.pedidos.application.servicio_pedidos import (
    ItemNuevoPedido,
    ServicioPedidos,
)


class RepoPedidosFalso:
    def __init__(self) -> None:
        self.items_creados: list[dict] = []

    async def cliente_valido(self, cliente_id: int) -> bool:
        return cliente_id == 1

    async def direccion_valida(self, cliente_id: int, direccion_id: int) -> bool:
        return True

    async def crear_direccion(self, cliente_id: int, datos: dict) -> int | None:
        return 1

    async def productos(self, ids: list[int]) -> list[dict]:
        return [
            {
                "id": 10,
                "nombre": "Bacon",
                "precio_base": Decimal("12000"),
                "variantes": [
                    {"nombre": "Simple", "precio": Decimal("12000")},
                    {"nombre": "Doble", "precio": Decimal("14500")},
                    {"nombre": "Triple", "precio": Decimal("16500")},
                ],
                "disponible": True,
            }
        ]

    async def crear(self, **datos) -> dict:
        self.items_creados = datos["items"]
        return {"id": 99}


class StockFalso:
    async def procesar(self, pedido_id: int, items: list[dict]) -> None:
        return None


@pytest.mark.asyncio
async def test_variante_define_precio_y_nombre_del_snapshot():
    repo = RepoPedidosFalso()
    servicio = ServicioPedidos(repo, StockFalso())

    await servicio.crear(
        cliente_id=1,
        tipo_entrega="RETIRO",
        direccion_id=None,
        direccion_nueva=None,
        observaciones=None,
        items=[ItemNuevoPedido(10, 2, variante="Triple")],
    )

    assert repo.items_creados == [
        {
            "producto_id": 10,
            "nombre_producto": "Bacon (Triple)",
            "cantidad": 2,
            "precio_unitario": Decimal("16500"),
            "aclaraciones": None,
        }
    ]


@pytest.mark.asyncio
async def test_rechaza_una_variante_que_no_existe():
    servicio = ServicioPedidos(RepoPedidosFalso(), StockFalso())

    with pytest.raises(DatosInvalidos, match="variante valida"):
        await servicio.crear(
            cliente_id=1,
            tipo_entrega="RETIRO",
            direccion_id=None,
            direccion_nueva=None,
            observaciones=None,
            items=[ItemNuevoPedido(10, 1, variante="Cuadruple")],
        )
