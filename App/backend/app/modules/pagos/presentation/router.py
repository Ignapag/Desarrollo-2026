"""Endpoints de la API para el módulo de pagos.

⚠️ PENDIENTE DE PROTECCIÓN: Al igual que en delivery, la guarda de autenticación
y rol del módulo de Usuarios y Seguridad (EDT 1.8) se agregará antes del parámetro
`servicio` cuando esté integrada.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencias import ServicioPagosDep
from app.modules.pagos.presentation.esquemas import (
    PagoSalida,
    RegistrarPagoEfectivoEntrada,
    ResultadoCobroEfectivoSalida,
)

router = APIRouter(prefix="/api/pagos", tags=["pagos"])


@router.post(
    "/efectivo",
    response_model=ResultadoCobroEfectivoSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar cobro en efectivo",
)
async def registrar_pago_efectivo(
    datos: RegistrarPagoEfectivoEntrada,
    servicio: ServicioPagosDep,
) -> ResultadoCobroEfectivoSalida:
    """Registra el cobro en efectivo de un pedido, calculando el vuelto correspondiente.

    - Si `conciliar_inmediato` es True, el pago queda en estado `CONCILIADO` inmediatamente.
    - Si el cobro cubre el total del pedido pendiente, el pedido pasa a estado `CONFIRMADO`.
    """
    resultado = await servicio.registrar_pago_efectivo(
        pedido_id=datos.pedido_id,
        monto_recibido=datos.monto_recibido,
        monto_a_pagar=datos.monto_a_pagar,
        propina=datos.propina,
        conciliar_inmediato=datos.conciliar_inmediato,
        registrado_por=datos.registrado_por,
    )
    return ResultadoCobroEfectivoSalida.desde_dominio(resultado)


@router.get(
    "/pedido/{pedido_id}",
    response_model=list[PagoSalida],
    summary="Listar pagos de un pedido",
)
async def listar_pagos_pedido(
    pedido_id: int,
    servicio: ServicioPagosDep,
) -> list[PagoSalida]:
    """Retorna el historial completo de pagos y egresos/devoluciones asociados a un pedido."""
    pagos = await servicio.listar_pagos_por_pedido(pedido_id)
    return [PagoSalida.desde_dominio(p) for p in pagos]


@router.get(
    "/{pago_id}",
    response_model=PagoSalida,
    summary="Obtener detalle de un pago",
)
async def obtener_pago(
    pago_id: int,
    servicio: ServicioPagosDep,
) -> PagoSalida:
    """Obtiene los datos de un pago registrado por su identificador primario."""
    pago = await servicio.obtener_pago(pago_id)
    return PagoSalida.desde_dominio(pago)
