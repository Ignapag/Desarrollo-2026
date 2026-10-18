"""El bot conserva la receta comprada al cambiar el catálogo posteriormente."""

from decimal import Decimal

import pytest

from app.modules.pedidos.domain.entidades import EstadoPedido
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from tests.test_whatsapp_regresiones import (
    TELEFONO,
    enviar,
    item_con_tomate,
    notas,
    nuevo_pedido,
    worker,
)

__all__ = ["worker"]


@pytest.mark.parametrize("cambio_catalogo", ["cantidad", "quitar"])
async def test_bot_usa_snapshot_para_contexto_y_devolucion_fraccionada(
    uow,
    worker,
    cambio_catalogo,
):
    item = await item_con_tomate(uow)
    producto_id = item["producto_id"]
    tomate_id = await uow.valor("SELECT id FROM ingrediente WHERE lower(nombre)='tomate'")
    saldo_inicial = await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s",
        (tomate_id,),
    )
    await uow.ejecutar(
        "UPDATE producto_ingrediente SET cantidad_requerida=0.250 "
        "WHERE producto_id=%s AND ingrediente_id=%s",
        (producto_id, tomate_id),
    )
    await uow.ejecutar(
        "UPDATE producto_variante_ingrediente SET cantidad_requerida=0.250 "
        "WHERE producto_id=%s AND ingrediente_id=%s",
        (producto_id, tomate_id),
    )

    servicio = construir_servicio(uow)
    _, pedido_id = await nuevo_pedido(uow, worker, servicio, "snapshot")
    snapshot = await uow.valor(
        "SELECT receta_snapshot FROM pedido_item WHERE pedido_id=%s",
        (pedido_id,),
    )
    assert next(
        Decimal(i["cantidad_requerida"]) for i in snapshot if i["ingrediente_id"] == tomate_id
    ) == Decimal("0.250")
    await servicio.pedidos.cambiar_estado(pedido_id, EstadoPedido.CONFIRMADO, usuario_id=None)
    assert await uow.valor(
        "SELECT cantidad_actual FROM ingrediente WHERE id=%s",
        (tomate_id,),
    ) == saldo_inicial - Decimal("0.250")

    if cambio_catalogo == "cantidad":
        await uow.ejecutar(
            "UPDATE producto_ingrediente SET cantidad_requerida=0.750 "
            "WHERE producto_id=%s AND ingrediente_id=%s",
            (producto_id, tomate_id),
        )
        await uow.ejecutar(
            "UPDATE producto_variante_ingrediente SET cantidad_requerida=0.750 "
            "WHERE producto_id=%s AND ingrediente_id=%s",
            (producto_id, tomate_id),
        )
    else:
        await uow.ejecutar(
            "DELETE FROM producto_variante_ingrediente WHERE producto_id=%s AND ingrediente_id=%s",
            (producto_id, tomate_id),
        )
        await uow.ejecutar(
            "DELETE FROM producto_ingrediente WHERE producto_id=%s AND ingrediente_id=%s",
            (producto_id, tomate_id),
        )
        assert all(
            i["nombre"].casefold() != "tomate"
            for i in await servicio.repo.ingredientes(producto_id)
        )

    await servicio.recibir("snapshot-sin-tomate", TELEFONO, "sin tomate")
    preparado = await servicio.preparar("snapshot-sin-tomate")
    assert "tomate" in {
        nombre.casefold() for nombre in preparado["contexto"]["items"][0]["ingredientes"]
    }
    await worker.procesar_entrada("snapshot-sin-tomate")
    respuesta = await uow.valor(
        "SELECT respuesta FROM whatsapp_entrada WHERE id='snapshot-sin-tomate'",
    )
    assert "Cambio guardado" in respuesta
    assert await notas(uow, pedido_id) == "Sin Tomate"

    respuesta = await enviar(
        uow,
        worker,
        servicio,
        "snapshot-sin-tomate-repetido",
        "sin tomate",
    )
    assert "ya está guardado sin ese ingrediente" in respuesta
    devoluciones = await uow.uno(
        "SELECT count(*) cantidad, sum(cantidad) devuelto FROM movimiento_stock "
        "WHERE pedido_id=%s AND ingrediente_id=%s AND tipo='DEVOLUCION'",
        (pedido_id, tomate_id),
    )
    assert devoluciones == {"cantidad": 1, "devuelto": Decimal("0.250")}
    assert (
        await uow.valor(
            "SELECT cantidad_actual FROM ingrediente WHERE id=%s",
            (tomate_id,),
        )
        == saldo_inicial
    )
    assert (
        await uow.valor(
            "SELECT receta_snapshot FROM pedido_item WHERE pedido_id=%s",
            (pedido_id,),
        )
        == snapshot
    )
