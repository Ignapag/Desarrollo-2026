"""Endpoints de la API para el módulo de pagos, cobro digital y webhooks.

⚠️ PENDIENTE DE PROTECCIÓN: Al igual que en delivery, la guarda de autenticación
y rol del módulo de Usuarios y Seguridad (EDT 1.8) se agregará antes del parámetro
`servicio` cuando esté integrada.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.core.dependencias import IpCliente, ServicioPagosDep
from app.modules.pagos.presentation.esquemas import (
    EstadoFinancieroPedidoSalida,
    IniciarCobroDigitalEntrada,
    PagoSalida,
    PreferenciaCobroSalida,
    RegistrarPagoEfectivoEntrada,
    ResultadoCobroEfectivoSalida,
    WebhookMercadoPagoEntrada,
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
    ip: IpCliente = None,
) -> ResultadoCobroEfectivoSalida:
    """Registra el cobro en efectivo de un pedido de forma concurrente-segura.

    - Bloqueo pesimista sobre el pedido (FOR UPDATE) para prevenir dobles cobros simultáneos.
    - Si `conciliar_inmediato` es True, el pago queda en estado `CONCILIADO` inmediatamente.
    - Si el cobro cubre el total del pedido pendiente, el pedido pasa a estado `CONFIRMADO`
      y se asienta en el historial de estados (`pedido_estado_historial`).
    - Registra el evento en auditoría con la IP del cliente.
    """
    resultado = await servicio.registrar_pago_efectivo(
        pedido_id=datos.pedido_id,
        monto_recibido=datos.monto_recibido,
        monto_a_pagar=datos.monto_a_pagar,
        propina=datos.propina,
        conciliar_inmediato=datos.conciliar_inmediato,
        registrado_por=datos.registrado_por,
        ip_cliente=ip,
    )
    return ResultadoCobroEfectivoSalida.desde_dominio(resultado)


@router.post(
    "/billetera/iniciar",
    response_model=PreferenciaCobroSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar cobro digital (Mercado Pago / Billeteras)",
)
async def iniciar_cobro_digital(
    datos: IniciarCobroDigitalEntrada,
    servicio: ServicioPagosDep,
    ip: IpCliente = None,
) -> PreferenciaCobroSalida:
    """Genera la orden de cobro digital (Checkout / QR dinámico de Mercado Pago o billeteras).

    - Asienta un pago PENDIENTE vinculado a la preferencia generada.
    - Devuelve el init_point para redirección web y el payload qr_data para pago con QR.
    """
    resultado = await servicio.iniciar_cobro_digital(
        pedido_id=datos.pedido_id,
        metodo_pago=datos.metodo_pago,
        monto_a_pagar=datos.monto_a_pagar,
        propina=datos.propina,
        payer_email=datos.payer_email,
        registrado_por=datos.registrado_por,
        ip_cliente=ip,
    )
    return PreferenciaCobroSalida(
        pago_id=resultado.pago.id,
        pedido_id=resultado.pago.pedido_id,
        metodo_pago=resultado.pago.metodo_pago,
        preference_id=resultado.preferencia.preference_id,
        init_point=resultado.preferencia.init_point,
        qr_data=resultado.preferencia.qr_data,
        monto=resultado.pago.monto,
        propina=resultado.pago.propina,
        estado=resultado.pago.estado,
    )


@router.post(
    "/webhook/mercadopago",
    summary="Receptor de notificaciones de pago (Webhook IPN)",
    status_code=status.HTTP_200_OK,
)
async def webhook_mercadopago(
    servicio: ServicioPagosDep,
    payload: WebhookMercadoPagoEntrada | None = None,
    topic: str | None = Query(default=None),
    id: str | None = Query(default=None),
    ip: IpCliente = None,
) -> dict:
    """Receptor oficial de webhooks e IPN de Mercado Pago.

    - Procesa eventos de tipo 'payment' de forma idempotente.
    - Si el pago fue acreditado ('approved'), actualiza el pago a CONCILIADO y confirma el pedido.
    - Si el pago fue rechazado, lo marca como ANULADO con su motivo.
    """
    # Mercado Pago envía el ID a través del query param o dentro de data.id del body
    payment_id = id
    if not payment_id and payload:
        if payload.data and "id" in payload.data:
            payment_id = str(payload.data["id"])
        elif payload.id:
            payment_id = str(payload.id)

    if not payment_id:
        return {"status": "ignorado", "motivo": "No se recibió identificador de recurso de pago"}

    return await servicio.procesar_webhook_mercadopago(
        payment_id=payment_id,
        topic=topic or (payload.type if payload else None),
        ip_cliente=ip,
    )


@router.get(
    "/pedido/{pedido_id}/estado",
    response_model=EstadoFinancieroPedidoSalida,
    summary="Consultar balance y estado financiero de un pedido",
)
async def estado_financiero_pedido(
    pedido_id: int,
    servicio: ServicioPagosDep,
) -> EstadoFinancieroPedidoSalida:
    """Retorna el balance de pagos, saldo pendiente, detalle de pagos y si el pedido está saldado."""
    estado = await servicio.obtener_estado_financiero(pedido_id)
    return EstadoFinancieroPedidoSalida.desde_dominio(estado)


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
