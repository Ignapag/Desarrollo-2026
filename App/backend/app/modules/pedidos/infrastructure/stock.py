"""Adaptador del puerto de consumo de stock requerido por Pedidos."""

from app.modules.stock.application.servicio_stock import ServicioStock
from app.modules.stock.domain.entidades import ItemConsumoStock


class AdaptadorConsumoStock:
    def __init__(self, servicio: ServicioStock) -> None:
        self.servicio = servicio

    async def procesar(self, pedido_id: int, items: list[dict]) -> None:
        await self.servicio.procesar_consumo(
            pedido_id,
            [
                ItemConsumoStock(
                    producto_id=item["producto_id"], cantidad=item["cantidad"], opciones=()
                )
                for item in items
            ],
        )
