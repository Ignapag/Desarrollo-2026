"""Buscador del panel de pedidos sobre PostgreSQL local: número, cliente y teléfono."""

import pytest

from app.modules.pedidos.presentation.dependencias import obtener_servicio_pedidos
from tests.test_stock_consumo_bd import crear_pedido, escenario

pytest_plugins = ("tests.test_stock_consumo_bd",)


async def pedido_de_demo(uow):
    """Pedido de un cliente del chat de demostración: el teléfono de WhatsApp es técnico
    (000…) y el real es el declarado en el checkout.
    """
    _, producto, _ = await escenario(uow)
    cliente = await uow.valor(
        "INSERT INTO cliente (nombre, telefono_whatsapp, telefono_contacto) "
        "VALUES ('Lucía Gómez', '000123456789012', '5492215551234') RETURNING id"
    )
    pedido, _ = await crear_pedido(uow, cliente, producto)
    numero = await uow.valor("SELECT numero FROM pedido WHERE id=%s", (pedido,))
    return pedido, numero


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "busqueda",
    [
        "{numero}",
        "#{numero}",
        "Pedido #{numero}",
        "lucía gómez",
        "lucia gomez",
        "5492215551234",
        "221 555-1234",
        "+54 9 221 555 1234",
    ],
)
async def test_busca_por_numero_cliente_y_telefono_tal_como_se_ven(uow, busqueda):
    pedido, numero = await pedido_de_demo(uow)
    filas = await obtener_servicio_pedidos(uow).listar(
        cliente_id=None, q=busqueda.format(numero=numero)
    )
    assert pedido in {fila["id"] for fila in filas}


@pytest.mark.asyncio
@pytest.mark.parametrize("busqueda", ["inexistente", "999 888 7777", "100%", "_"])
async def test_no_devuelve_pedidos_que_no_coinciden(uow, busqueda):
    pedido, _ = await pedido_de_demo(uow)
    filas = await obtener_servicio_pedidos(uow).listar(cliente_id=None, q=busqueda)
    assert pedido not in {fila["id"] for fila in filas}
