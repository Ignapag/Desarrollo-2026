"""Esquemas Pydantic V2 para validación de entrada y serialización de salida."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.pagos.domain.entidades import (
    CierreCaja,
    ConsolidadoTurno,
    EstadoCierre,
    EstadoFinancieroPedido,
    EstadoPago,
    MetodoPago,
    Pago,
    ResultadoCobroEfectivo,
    TipoPago,
    TotalesMetodoPago,
    TurnoCierre,
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


class TotalesMetodoPagoSalida(BaseModel):
    """Subtotal y cantidad por método de pago."""

    metodo_pago: MetodoPago
    total: Decimal
    cantidad: int

    @classmethod
    def desde_dominio(cls, item: TotalesMetodoPago) -> TotalesMetodoPagoSalida:
        return cls(
            metodo_pago=item.metodo_pago,
            total=item.total,
            cantidad=item.cantidad,
        )


class ConsolidadoTurnoSalida(BaseModel):
    """Resumen consolidado de ingresos y egresos de un turno."""

    fecha: date
    turno: TurnoCierre
    desde: datetime
    hasta: datetime
    total_efectivo: Decimal
    total_billeteras: Decimal
    total_devoluciones: Decimal
    total_general: Decimal
    total_propinas: Decimal
    cantidad_pedidos: int
    cantidad_pagos: int
    pagos_pendientes_conciliacion: int
    desglose_metodos: list[TotalesMetodoPagoSalida]

    @classmethod
    def desde_dominio(cls, c: ConsolidadoTurno) -> ConsolidadoTurnoSalida:
        return cls(
            fecha=c.fecha,
            turno=c.turno,
            desde=c.desde,
            hasta=c.hasta,
            total_efectivo=c.total_efectivo,
            total_billeteras=c.total_billeteras,
            total_devoluciones=c.total_devoluciones,
            total_general=c.total_general,
            total_propinas=c.total_propinas,
            cantidad_pedidos=c.cantidad_pedidos,
            cantidad_pagos=c.cantidad_pagos,
            pagos_pendientes_conciliacion=c.pagos_pendientes_conciliacion,
            desglose_metodos=[TotalesMetodoPagoSalida.desde_dominio(m) for m in c.desglose_metodos],
        )


class GenerarCierreEntrada(BaseModel):
    """Parámetros para generar o recalcular el resumen de cierre de caja."""

    model_config = ConfigDict(extra="forbid")

    fecha: date | None = Field(
        default=None,
        description="Fecha contable a cerrar (si se omite, se deduce automáticamente)",
    )
    turno: TurnoCierre | None = Field(
        default=None,
        description="Turno a cerrar (MEDIODIA o NOCHE; si se omite, se deduce automáticamente)",
    )
    observaciones: str | None = Field(
        default=None,
        description="Notas u observaciones del arqueo de caja",
    )
    generado_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario/empleado que ejecuta el cierre",
    )


class CierreCajaSalida(BaseModel):
    """Detalle del registro de cierre de caja."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    turno: TurnoCierre
    abierto_en: datetime
    cerrado_en: datetime | None
    total_efectivo: Decimal
    total_billeteras: Decimal
    total_devoluciones: Decimal
    total_general: Decimal
    cantidad_pedidos: int
    estado: EstadoCierre
    generado_por: int | None
    aprobado_por: int | None
    aprobado_en: datetime | None
    observaciones: str | None

    @classmethod
    def desde_dominio(cls, c: CierreCaja) -> CierreCajaSalida:
        return cls(
            id=c.id,
            fecha=c.fecha,
            turno=c.turno,
            abierto_en=c.abierto_en,
            cerrado_en=c.cerrado_en,
            total_efectivo=c.total_efectivo,
            total_billeteras=c.total_billeteras,
            total_devoluciones=c.total_devoluciones,
            total_general=c.total_general,
            cantidad_pedidos=c.cantidad_pedidos,
            estado=c.estado,
            generado_por=c.generado_por,
            aprobado_por=c.aprobado_por,
            aprobado_en=c.aprobado_en,
            observaciones=c.observaciones,
        )


class AprobarCierreEntrada(BaseModel):
    """Datos para aprobar formalmente y bloquear un cierre de caja."""

    model_config = ConfigDict(extra="forbid")

    aprobado_por: int = Field(
        ...,
        gt=0,
        description="ID del dueño o supervisor que aprueba el cierre",
    )
    observaciones: str | None = Field(
        default=None,
        description="Observaciones finales de revisión y conformidad",
    )


class ConciliarPagoEntrada(BaseModel):
    """Datos para conciliar un pago individual."""

    model_config = ConfigDict(extra="forbid")

    conciliar_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario/cajero que valida la conciliación",
    )
    comprobante: str | None = Field(
        default=None,
        description="Número de comprobante bancario o referencia externa",
    )


class ConciliarLoteEntrada(BaseModel):
    """Datos para conciliar múltiples pagos en lote."""

    model_config = ConfigDict(extra="forbid")

    pago_ids: list[int] = Field(
        ...,
        min_length=1,
        description="Lista de IDs de pagos a conciliar",
    )
    conciliar_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario que ejecuta la conciliación",
    )


class RegistrarDevolucionEntrada(BaseModel):
    """Datos para registrar un egreso o devolución sobre un pedido (C-11)."""

    model_config = ConfigDict(extra="forbid")

    pedido_id: int = Field(..., gt=0, description="ID del pedido sobre el que se efectúa la devolución")
    monto: Decimal = Field(..., gt=0, description="Monto a devolver/reintegrar")
    motivo: str = Field(..., min_length=3, description="Explicación detallada del reintegro")
    metodo_pago: MetodoPago = Field(
        default=MetodoPago.EFECTIVO,
        description="Medio por el cual se reintegra el dinero",
    )
    registrado_por: int | None = Field(
        default=None,
        gt=0,
        description="ID del usuario que procesa la devolución",
    )


class AnularPagoEntrada(BaseModel):
    """Datos para anular un pago pendiente."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(..., min_length=3, description="Motivo de la anulación")
    anulado_por: int | None = Field(default=None, gt=0, description="ID del usuario que anula")


class ResultadoConciliacionLoteSalida(BaseModel):
    """Resultado del procesamiento de conciliación en lote."""

    conciliados: list[int]
    fallidos: list[dict]
    total_procesados: int




