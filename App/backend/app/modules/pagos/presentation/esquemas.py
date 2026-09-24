"""Esquemas Pydantic V2 para validación de entrada y serialización de salida."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pagos.domain.entidades import (
    EstadoFinancieroPedido,
    EstadoPago,
    MetodoPago,
    Pago,
    ResultadoCobroEfectivo,
    TipoPago,
)


class RegistrarPagoEfectivoEntrada(BaseModel):
    """Datos para registrar un cobro en efectivo."""

    model_config = ConfigDict(extra="forbid")

    pedido_id: int = Field(..., gt=0, description="ID del pedido que se abona")
    monto_recibido: Decimal = Field(
        ...,
        gt=0,
        description="Monto en efectivo entregado físicamente por el cliente (para calcular el vuelto)",
    )
    monto_a_pagar: Decimal | None = Field(
        default=None,
        gt=0,
        description="Monto específico a cobrar. Si no se envía, se toma el saldo pendiente completo",
    )
    propina: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Monto de propina voluntaria entregada por el cliente",
    )
    conciliar_inmediato: bool = Field(
        default=True,
        description="True para cobro inmediato en mostrador (queda CONCILIADO); False para entrega pendiente",
    )
    registrado_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario/empleado que recibe el dinero",
    )


class IniciarCobroDigitalEntrada(BaseModel):
    """Datos para iniciar un cobro mediante billetera virtual (Mercado Pago, Cuenta DNI, etc.)."""

    model_config = ConfigDict(extra="forbid")

    pedido_id: int = Field(..., gt=0, description="ID del pedido a cobrar")
    metodo_pago: MetodoPago = Field(
        default=MetodoPago.MERCADO_PAGO,
        description="Billetera virtual seleccionada (MERCADO_PAGO, CUENTA_DNI, NARANJA_X, OTRA_BILLETERA, TRANSFERENCIA)",
    )
    monto_a_pagar: Decimal | None = Field(
        default=None,
        gt=0,
        description="Monto a imputar (si se omite, se cobra el saldo pendiente total)",
    )
    propina: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Propina opcional",
    )
    payer_email: str | None = Field(
        default=None,
        description="Email del cliente para asociar a la preferencia",
    )
    registrado_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario/empleado que genera la orden",
    )


class PreferenciaCobroSalida(BaseModel):
    """Respuesta con los datos de cobro digital (Checkout y QR)."""

    pago_id: int
    pedido_id: int
    metodo_pago: MetodoPago
    preference_id: str
    init_point: str
    qr_data: str
    monto: Decimal
    propina: Decimal
    estado: EstadoPago


class WebhookMercadoPagoEntrada(BaseModel):
    """Payload recibido en el webhook de Mercado Pago."""

    model_config = ConfigDict(extra="ignore")

    action: str | None = None
    api_version: str | None = None
    data: dict | None = None
    id: str | int | None = None
    type: str | None = None
    topic: str | None = None


class PagoSalida(BaseModel):
    """Representación de un pago o egreso."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    pedido_id: int
    cierre_caja_id: int | None
    tipo: TipoPago
    metodo_pago: MetodoPago
    monto: Decimal
    propina: Decimal
    estado: EstadoPago
    referencia_externa: str | None
    registrado_por: int | None
    registrado_en: datetime
    conciliado_en: datetime | None
    motivo: str | None

    @classmethod
    def desde_dominio(cls, pago: Pago) -> PagoSalida:
        return cls(
            id=pago.id,
            pedido_id=pago.pedido_id,
            cierre_caja_id=pago.cierre_caja_id,
            tipo=pago.tipo,
            metodo_pago=pago.metodo_pago,
            monto=pago.monto,
            propina=pago.propina,
            estado=pago.estado,
            referencia_externa=pago.referencia_externa,
            registrado_por=pago.registrado_por,
            registrado_en=pago.registrado_en,
            conciliado_en=pago.conciliado_en,
            motivo=pago.motivo,
        )


class DetalleCobroEfectivoSalida(BaseModel):
    """Desglose financiero del cobro en efectivo."""

    total_pedido: Decimal
    monto_cobrado: Decimal
    propina: Decimal
    monto_recibido: Decimal
    vuelto: Decimal
    saldo_restante: Decimal


class ResultadoCobroEfectivoSalida(BaseModel):
    """Respuesta completa tras registrar exitosamente el pago en efectivo."""

    pago: PagoSalida
    detalle: DetalleCobroEfectivoSalida

    @classmethod
    def desde_dominio(cls, res: ResultadoCobroEfectivo) -> ResultadoCobroEfectivoSalida:
        return cls(
            pago=PagoSalida.desde_dominio(res.pago),
            detalle=DetalleCobroEfectivoSalida(
                total_pedido=res.detalle.total_pedido,
                monto_cobrado=res.detalle.monto_cobrado,
                propina=res.detalle.propina,
                monto_recibido=res.detalle.monto_recibido,
                vuelto=res.detalle.vuelto,
                saldo_restante=res.detalle.saldo_restante,
            ),
        )


class EstadoFinancieroPedidoSalida(BaseModel):
    """Estado financiero consolidado de un pedido."""

    pedido_id: int
    numero: int
    estado_pedido: str
    total_pedido: Decimal
    total_pagado: Decimal
    saldo_pendiente: Decimal
    esta_saldado: bool
    cantidad_pagos: int
    pagos: list[PagoSalida]

    @classmethod
    def desde_dominio(cls, estado: EstadoFinancieroPedido) -> EstadoFinancieroPedidoSalida:
        return cls(
            pedido_id=estado.pedido_id,
            numero=estado.numero,
            estado_pedido=estado.estado_pedido,
            total_pedido=estado.total_pedido,
            total_pagado=estado.total_pagado,
            saldo_pendiente=estado.saldo_pendiente,
            esta_saldado=estado.esta_saldado,
            cantidad_pagos=estado.cantidad_pagos,
            pagos=[PagoSalida.desde_dominio(p) for p in estado.pagos],
        )
