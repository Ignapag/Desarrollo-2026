"""Estados y transiciones puras de pedidos."""

from enum import StrEnum


class EstadoPedido(StrEnum):
    """Estados del ciclo de vida de un pedido, desde su captura hasta la entrega o cancelación."""

    PENDIENTE = "PENDIENTE"
    CONFIRMADO = "CONFIRMADO"
    EN_PREPARACION = "EN_PREPARACION"
    LISTO = "LISTO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"


# Transiciones normales permitidas; las correcciones y recuperaciones se validan aparte.
TRANSICIONES: dict[EstadoPedido, frozenset[EstadoPedido]] = {
    EstadoPedido.PENDIENTE: frozenset(
        {EstadoPedido.CONFIRMADO, EstadoPedido.EN_PREPARACION, EstadoPedido.CANCELADO}
    ),
    EstadoPedido.CONFIRMADO: frozenset(
        {EstadoPedido.EN_PREPARACION, EstadoPedido.CANCELADO}
    ),
    EstadoPedido.EN_PREPARACION: frozenset({EstadoPedido.LISTO}),
    EstadoPedido.LISTO: frozenset({EstadoPedido.EN_CAMINO}),
    EstadoPedido.EN_CAMINO: frozenset({EstadoPedido.ENTREGADO}),
    EstadoPedido.ENTREGADO: frozenset(),
    EstadoPedido.CANCELADO: frozenset(),
}


def puede_transicionar(actual: EstadoPedido, nuevo: EstadoPedido) -> bool:
    """Indica si el pedido puede pasar de ``actual`` a ``nuevo`` en el flujo normal."""
    return nuevo in TRANSICIONES[actual]
