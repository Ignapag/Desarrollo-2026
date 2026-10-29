"""No cerrar una entrega con deuda; conservar recuperables los saldos históricos."""

from decimal import Decimal

import pytest

from app.errores import ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido
from tests.test_edicion_items_bd import crear


async def listo(uow, metodo):
    servicio, pedido, _, _ = await crear(uow)
    pedido = await servicio.cambiar_estado(
        pedido["id"], EstadoPedido.EN_PREPARACION, usuario_id=None
    )
    pedido = await servicio.cambiar_estado(pedido["id"], EstadoPedido.LISTO, usuario_id=None)
    await uow.ejecutar(
        "UPDATE pedido SET metodo_pago_acordado=%s WHERE id=%s", (metodo, pedido["id"])
    )
    return servicio, pedido


async def cobro(uow, pedido_id, monto, *, estado="CONCILIADO", tipo="COBRO"):
    await uow.ejecutar(
        "INSERT INTO pago(pedido_id,tipo,metodo_pago,monto,estado) "
        "VALUES(%s,%s,'EFECTIVO',%s,%s)", (pedido_id, tipo, monto, estado),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("metodo", ["EFECTIVO", "TRANSFERENCIA"])
@pytest.mark.parametrize("situacion", ["sin_pago", "pendiente", "parcial", "devuelto"])
async def test_retiro_con_deuda_no_cambia_estado_ni_crea_pago(uow, metodo, situacion):
    servicio, pedido = await listo(uow, metodo)
    if situacion == "pendiente":
        await cobro(uow, pedido["id"], 100, estado="PENDIENTE")
    elif situacion == "parcial":
        await cobro(uow, pedido["id"], 50)
    elif situacion == "devuelto":
        await cobro(uow, pedido["id"], 100)
        await cobro(uow, pedido["id"], 1, tipo="DEVOLUCION")
    pagos = await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido["id"],))
    with pytest.raises(ReglaDeNegocio, match="pago completo"):
        await servicio.cambiar_estado(pedido["id"], EstadoPedido.ENTREGADO, usuario_id=None)
    actual = await servicio.detalle(pedido["id"])
    assert actual["estado"] == "LISTO"
    assert actual["version"] == pedido["version"]
    assert await uow.valor(
        "SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido["id"],)
    ) == pagos


@pytest.mark.asyncio
@pytest.mark.parametrize("metodo", ["EFECTIVO", "TRANSFERENCIA"])
async def test_retiro_cubierto_se_entrega_sin_cobrar_de_nuevo(uow, metodo):
    servicio, pedido = await listo(uow, metodo)
    await cobro(uow, pedido["id"], Decimal("100"))
    resultado = await servicio.cambiar_estado(
        pedido["id"], EstadoPedido.ENTREGADO, usuario_id=None
    )
    assert resultado["estado"] == "ENTREGADO"
    assert resultado["neto_cobrado"] == resultado["total"]
    assert await uow.valor(
        "SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido["id"],)
    ) == 1


@pytest.mark.asyncio
async def test_entregado_heredado_con_deuda_sigue_cobrable_en_activos(uow):
    servicio, pedido = await listo(uow, "EFECTIVO")
    await uow.ejecutar(
        "UPDATE pedido SET estado='ENTREGADO',entregado_en=now() WHERE id=%s", (pedido["id"],)
    )
    activos = await servicio.listar(activos=True)
    assert pedido["id"] in {p["id"] for p in activos}
    await cobro(uow, pedido["id"], 100)
    activos = await servicio.listar(activos=True)
    assert pedido["id"] not in {p["id"] for p in activos}
    historicos = await servicio.listar(activos=False)
    assert pedido["id"] in {p["id"] for p in historicos}
