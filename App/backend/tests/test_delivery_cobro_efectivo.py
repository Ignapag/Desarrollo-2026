"""Cobro en efectivo del repartidor en la puerta, sobre PostgreSQL local."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.errores import DatosInvalidos, ReglaDeNegocio, SinPermiso
from app.modules.delivery.presentation.dependencias import obtener_servicio_delivery
from tests.test_delivery_bd import ENSENADA_CENTRO, crear_pedido_listo, liberar_repartidores

TOTAL = Decimal("12000.00")


async def envio_con_saldo(uow, servicio, sufijo, *, salir=True):
    """Pedido delivery de $12.000 sin cobros, asignado a un viaje (en ruta si ``salir``)."""
    await liberar_repartidores(uow)
    pedido = await crear_pedido_listo(uow, sufijo, ENSENADA_CENTRO)
    await uow.ejecutar(
        "UPDATE pedido SET subtotal=%s,total=%s,metodo_pago_acordado='EFECTIVO' WHERE id=%s",
        (TOTAL, TOTAL, pedido),
    )
    resultado = await servicio.planificar_y_asignar()
    viaje = next(v for v in resultado.viajes if pedido in v.pedidos)
    if salir:
        await servicio.iniciar_viaje(viaje.viaje_id)
    envio = await uow.valor("SELECT id FROM envio WHERE pedido_id=%s", (pedido,))
    return pedido, envio, viaje.repartidor_id


@pytest.mark.asyncio
async def test_repartidor_cobra_en_efectivo_y_entrega_sin_llamar_al_local(uow):
    servicio = obtener_servicio_delivery(uow)
    pedido, envio, repartidor = await envio_con_saldo(uow, servicio, "ce1")
    with pytest.raises(ReglaDeNegocio):
        await servicio.registrar_entrega(envio, usuario_id=repartidor, rol="REPARTIDOR")
    clave = str(uuid4())
    for _ in range(2):  # el reintento con la misma clave no duplica el cobro
        cobro = await servicio.cobrar_en_efectivo(
            envio, monto=TOTAL, clave_operacion=clave, usuario_id=repartidor, rol="REPARTIDOR"
        )
        assert cobro["monto_cobrado"] == TOTAL and cobro["saldo_restante"] == 0
    pagos = await uow.todos(
        "SELECT metodo_pago,estado,monto,registrado_por FROM pago WHERE pedido_id=%s", (pedido,)
    )
    assert pagos == [{"metodo_pago": "EFECTIVO", "estado": "CONCILIADO", "monto": TOTAL,
                      "registrado_por": repartidor}]
    entrega = await servicio.registrar_entrega(envio, usuario_id=repartidor, rol="REPARTIDOR")
    assert entrega["pedido_id"] == pedido
    assert await uow.valor("SELECT estado FROM pedido WHERE id=%s", (pedido,)) == "ENTREGADO"


@pytest.mark.asyncio
async def test_otro_repartidor_no_puede_cobrar_el_envio(uow):
    servicio = obtener_servicio_delivery(uow)
    pedido, envio, repartidor = await envio_con_saldo(uow, servicio, "ce2")
    with pytest.raises(SinPermiso):
        await servicio.cobrar_en_efectivo(
            envio, monto=TOTAL, clave_operacion=str(uuid4()),
            usuario_id=repartidor + 100000, rol="REPARTIDOR",
        )
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido,)) == 0


@pytest.mark.asyncio
async def test_no_se_cobra_antes_de_salir_ni_por_encima_del_saldo(uow):
    servicio = obtener_servicio_delivery(uow)
    pedido, envio, repartidor = await envio_con_saldo(uow, servicio, "ce3", salir=False)
    with pytest.raises(ReglaDeNegocio):
        await servicio.cobrar_en_efectivo(
            envio, monto=TOTAL, clave_operacion=str(uuid4()),
            usuario_id=repartidor, rol="REPARTIDOR",
        )
    viaje = await uow.valor("SELECT viaje_id FROM envio WHERE id=%s", (envio,))
    await servicio.iniciar_viaje(viaje)
    with pytest.raises(DatosInvalidos):
        await servicio.cobrar_en_efectivo(
            envio, monto=TOTAL + 1, clave_operacion=str(uuid4()),
            usuario_id=repartidor, rol="REPARTIDOR",
        )
    assert await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (pedido,)) == 0
