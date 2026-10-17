"""Adaptador del puerto de consumo de stock requerido por Pedidos."""

from app.modules.stock.application.servicio_stock import PedidoYaProcesado, ServicioStock
from app.modules.stock.domain.entidades import INGREDIENTES_QUITABLES, ItemConsumoStock


def ingredientes_omitidos(aclaraciones: str | None) -> tuple[str, ...]:
    """Solo interpreta listas completas de retiros conocidos, nunca texto libre."""
    if not aclaraciones:
        return ()
    notas = [nota.strip().casefold() for nota in aclaraciones.split(",")]
    if any(not nota.startswith("sin ") or nota[4:] not in INGREDIENTES_QUITABLES
           for nota in notas):
        return ()
    return tuple(nota[4:] for nota in notas)


class AdaptadorConsumoStock:
    def __init__(self, servicio: ServicioStock) -> None:
        self.servicio = servicio

    async def procesar(self, pedido_id: int, items: list[dict]) -> None:
        try:
            await self.servicio.procesar_consumo(
                pedido_id,
                [
                    ItemConsumoStock(
                        producto_id=item["producto_id"], cantidad=item["cantidad"], opciones=(),
                        ingredientes_omitidos=ingredientes_omitidos(item.get("aclaraciones")),
                    )
                    for item in items
                ],
            )
        except PedidoYaProcesado:
            # Confirmacion y preparacion pueden pasar por la misma transaccion
            # de consumo; solo el duplicado probado por Stock es idempotente.
            return
