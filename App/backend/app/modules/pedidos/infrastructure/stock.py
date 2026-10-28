"""Adaptador del puerto de consumo de stock requerido por Pedidos."""

from app.modules.stock.application.servicio_stock import PedidoYaProcesado, ServicioStock
from app.modules.stock.domain.entidades import (
    INGREDIENTES_QUITABLES,
    ItemConsumoStock,
    cantidades_de_snapshot,
)


def ingredientes_omitidos(aclaraciones: str | None) -> tuple[str, ...]:
    """Solo interpreta listas completas de retiros conocidos, nunca texto libre."""
    if not aclaraciones:
        return ()
    notas = [nota.strip().casefold() for nota in aclaraciones.split(",")]
    # Si alguna nota no es un retiro conocido, se ignora todo para no descontar de menos.
    if any(not nota.startswith("sin ") or nota[4:] not in INGREDIENTES_QUITABLES for nota in notas):
        return ()
    return tuple(nota[4:] for nota in notas)


class AdaptadorConsumoStock:
    """Adapta el servicio de stock al puerto ``ProcesadorStock`` que usa Pedidos.

    Convierte las líneas del pedido en ``ItemConsumoStock`` respetando ingredientes retirados y la
    receta congelada al momento de la compra.
    """

    def __init__(self, servicio: ServicioStock) -> None:
        """Recibe el servicio de stock que comparte la transacción del pedido."""
        self.servicio = servicio

    async def ajustar_composicion(
        self, pedido_id: int, anteriores: list[dict], nuevos: list[dict],
        version: int, usuario_id: int | None, *, aplicar: bool,
    ) -> None:
        """Ajusta reservas y consumos de stock ante un cambio de composición del pedido.

        Con ``aplicar=False`` solo valida (cotización) sin modificar el stock.
        """
        def convertir(items):
            """Convierte líneas del pedido en ítems de consumo de stock."""
            return [
                ItemConsumoStock(
                    item["producto_id"], item["cantidad"],
                    ingredientes_omitidos=ingredientes_omitidos(item.get("aclaraciones")),
                    receta_snapshot=cantidades_de_snapshot(item.get("receta_snapshot")),
                )
                for item in items
            ]

        await self.servicio.ajustar_composicion(
            pedido_id, convertir(anteriores), convertir(nuevos), version,
            usuario_id, aplicar=aplicar,
        )

    async def devolver_reserva(self, pedido_id: int, usuario_id: int | None) -> None:
        """Devuelve al stock la reserva de un pedido cancelado antes de cocina."""
        await self.servicio.devolver_reserva_pedido(pedido_id, usuario_id)

    async def reconsumir(
        self, pedido_id: int, items: list[dict], version: int, usuario_id: int | None
    ) -> None:
        """Vuelve a consumir stock al recuperar un pedido cerrado, en un ciclo nuevo."""
        await self.servicio.procesar_consumo(
            pedido_id,
            [
                ItemConsumoStock(
                    item["producto_id"],
                    item["cantidad"],
                    ingredientes_omitidos=ingredientes_omitidos(item.get("aclaraciones")),
                    receta_snapshot=cantidades_de_snapshot(item.get("receta_snapshot")),
                )
                for item in items
            ],
            clave_ciclo=f"REAPERTURA:v{version}",
            usuario_id=usuario_id,
        )

    async def procesar(self, pedido_id: int, items: list[dict]) -> None:
        """Consume el stock de las líneas del pedido al confirmarlo o prepararlo."""
        try:
            await self.servicio.procesar_consumo(
                pedido_id,
                [
                    ItemConsumoStock(
                        producto_id=item["producto_id"],
                        cantidad=item["cantidad"],
                        opciones=(),
                        ingredientes_omitidos=ingredientes_omitidos(item.get("aclaraciones")),
                        receta_snapshot=cantidades_de_snapshot(item.get("receta_snapshot")),
                    )
                    for item in items
                ],
            )
        except PedidoYaProcesado:
            # Confirmacion y preparacion pueden pasar por la misma transaccion
            # de consumo; solo el duplicado probado por Stock es idempotente.
            return
