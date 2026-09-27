"""Entidades y reglas del dominio de pagos y caja.

Lógica pura de negocio: dataclasses inmutables, enums y validaciones
sin dependencias de infraestructura ni frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

from app.core.errores import DatosInvalidos, ReglaDeNegocio


class TipoPago(StrEnum):
    COBRO = "COBRO"
    DEVOLUCION = "DEVOLUCION"


class MetodoPago(StrEnum):
    EFECTIVO = "EFECTIVO"
    MERCADO_PAGO = "MERCADO_PAGO"
    CUENTA_DNI = "CUENTA_DNI"
    NARANJA_X = "NARANJA_X"
    OTRA_BILLETERA = "OTRA_BILLETERA"
    TRANSFERENCIA = "TRANSFERENCIA"


class EstadoPago(StrEnum):
    PENDIENTE = "PENDIENTE"
    CONCILIADO = "CONCILIADO"
    ANULADO = "ANULADO"


class TurnoCierre(StrEnum):
    MEDIODIA = "MEDIODIA"
    NOCHE = "NOCHE"


class EstadoCierre(StrEnum):
    ABIERTO = "ABIERTO"
    PENDIENTE_APROBACION = "PENDIENTE_APROBACION"
    APROBADO = "APROBADO"


class AccionesPagos:
    """Constantes de acciones para la auditoría (RNF-09)."""

    PAGO_REGISTRADO = "PAGO_REGISTRADO"
    PAGO_CONCILIADO = "PAGO_CONCILIADO"
    PAGO_ANULADO = "PAGO_ANULADO"
    DEVOLUCION_REGISTRADA = "DEVOLUCION_REGISTRADA"
    CIERRE_GENERADO = "CIERRE_GENERADO"
    CIERRE_APROBADO = "CIERRE_APROBADO"


@dataclass(slots=True, frozen=True)
class Pago:
    """Entidad que representa un pago o devolución registrado en el sistema."""

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

    @property
    def es_cobro(self) -> bool:
        return self.tipo == TipoPago.COBRO

    @property
    def es_conciliado(self) -> bool:
        return self.estado == EstadoPago.CONCILIADO

    def validar_inmutabilidad(
        self,
        nuevo_monto: Decimal,
        nuevo_metodo: MetodoPago,
        nueva_propina: Decimal,
        nuevo_pedido_id: int,
    ) -> None:
        """Protección del alcance: un pago conciliado es inalterable en sus atributos críticos."""
        if self.es_conciliado:
            if (
                self.monto != nuevo_monto
                or self.metodo_pago != nuevo_metodo
                or self.propina != nueva_propina
                or self.pedido_id != nuevo_pedido_id
            ):
                raise ReglaDeNegocio(
                    f"No se puede modificar un pago ya conciliado (pago #{self.id})"
                )


@dataclass(slots=True, frozen=True)
class DetalleCobroEfectivo:
    """Resultado del cálculo y desglose de un cobro en efectivo."""

    total_pedido: Decimal
    monto_cobrado: Decimal
    propina: Decimal
    monto_recibido: Decimal
    vuelto: Decimal
    saldo_restante: Decimal


@dataclass(slots=True, frozen=True)
class ResultadoCobroEfectivo:
    """Entidad resultado de procesar un cobro en efectivo."""

    pago: Pago
    detalle: DetalleCobroEfectivo


@dataclass(slots=True, frozen=True)
class EstadoFinancieroPedido:
    """Resumen consolidado de la situación de pagos de un pedido."""

    pedido_id: int
    numero: int
    estado_pedido: str
    total_pedido: Decimal
    total_pagado: Decimal
    saldo_pendiente: Decimal
    esta_saldado: bool
    cantidad_pagos: int
    pagos: list[Pago]


@dataclass(slots=True, frozen=True)
class TotalesMetodoPago:
    """Acumulados y conteo de pagos por cada método."""

    metodo_pago: MetodoPago
    total: Decimal
    cantidad: int


@dataclass(slots=True, frozen=True)
class ConsolidadoTurno:
    """Totales consolidados de ingresos y egresos de un turno."""

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
    desglose_metodos: list[TotalesMetodoPago]


@dataclass(slots=True, frozen=True)
class CierreCaja:
    """Entidad que representa el cierre formal de caja de un turno."""

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

    @property
    def es_aprobado(self) -> bool:
        return self.estado == EstadoCierre.APROBADO

    def validar_inmutabilidad(self) -> None:
        """Garantiza la regla de negocio del alcance: un cierre aprobado es inalterable."""
        if self.es_aprobado:
            raise ReglaDeNegocio(
                f"El cierre de caja #{self.id} ya fue aprobado y es inalterable"
            )


def calcular_cobro_efectivo(
    total_pedido: Decimal,
    total_ya_pagado: Decimal,
    monto_recibido: Decimal,
    monto_a_pagar: Decimal | None = None,
    propina: Decimal = Decimal("0.00"),
) -> DetalleCobroEfectivo:
    """Calcula el cobro en efectivo, validando importes y vuelto."""
    if propina < Decimal("0.00"):
        raise DatosInvalidos("La propina no puede ser negativa")

    saldo_pendiente = max(Decimal("0.00"), total_pedido - total_ya_pagado)
    if saldo_pendiente == Decimal("0.00"):
        raise ReglaDeNegocio("El pedido ya se encuentra totalmente saldado")

    a_cobrar = monto_a_pagar if monto_a_pagar is not None else saldo_pendiente

    if a_cobrar <= Decimal("0.00"):
        raise DatosInvalidos("El monto a pagar debe ser mayor a cero")

    if a_cobrar > saldo_pendiente:
        raise DatosInvalidos(
            f"El monto a cobrar (${a_cobrar}) supera el saldo pendiente (${saldo_pendiente})"
        )

    total_necesario = a_cobrar + propina
    if monto_recibido < total_necesario:
        raise DatosInvalidos(
            f"El dinero recibido (${monto_recibido}) no alcanza para cubrir el cobro (${a_cobrar}) "
            f"y la propina (${propina}). Faltan ${total_necesario - monto_recibido}"
        )

    vuelto = monto_recibido - total_necesario
    nuevo_saldo = saldo_pendiente - a_cobrar

    return DetalleCobroEfectivo(
        total_pedido=total_pedido,
        monto_cobrado=a_cobrar,
        propina=propina,
        monto_recibido=monto_recibido,
        vuelto=vuelto,
        saldo_restante=nuevo_saldo,
    )


def calcular_estado_financiero(
    pedido_id: int,
    numero: int,
    estado_pedido: str,
    total_pedido: Decimal,
    pagos: list[Pago],
) -> EstadoFinancieroPedido:
    """Calcula el balance y estado financiero de un pedido en base a sus pagos registrados."""
    total_cobros = sum(
        (p.monto for p in pagos if p.es_cobro and p.estado != EstadoPago.ANULADO),
        Decimal("0.00"),
    )
    total_devoluciones = sum(
        (p.monto for p in pagos if not p.es_cobro and p.estado != EstadoPago.ANULADO),
        Decimal("0.00"),
    )
    total_neto = total_cobros - total_devoluciones
    saldo_pendiente = max(Decimal("0.00"), total_pedido - total_neto)
    esta_saldado = (saldo_pendiente == Decimal("0.00")) and (total_neto >= total_pedido)

    return EstadoFinancieroPedido(
        pedido_id=pedido_id,
        numero=numero,
        estado_pedido=estado_pedido,
        total_pedido=total_pedido,
        total_pagado=total_neto,
        saldo_pendiente=saldo_pendiente,
        esta_saldado=esta_saldado,
        cantidad_pagos=len(pagos),
        pagos=pagos,
    )


def determinar_turno_y_ventana(
    momento: datetime | None = None,
) -> tuple[TurnoCierre, date, datetime, datetime]:
    """Determina el turno, fecha contable y rango de tiempo [desde, hasta].

    Reglas de horarios de Monu Burger:
    - Turno MEDIODIA: 10:00 a 16:59:59 del mismo día.
    - Turno NOCHE: 17:00 a 04:59:59 del día siguiente.
      Si el momento actual es de madrugada (00:00 a 04:59), la fecha contable
      corresponde al día anterior.
    """
    if momento is None:
        momento = datetime.now()

    if momento.hour < 5:
        fecha_caja = momento.date() - timedelta(days=1)
        turno = TurnoCierre.NOCHE
        desde = datetime.combine(fecha_caja, time(17, 0, 0), tzinfo=momento.tzinfo)
        hasta = datetime.combine(momento.date(), time(4, 59, 59), tzinfo=momento.tzinfo)
    elif momento.hour < 17:
        fecha_caja = momento.date()
        turno = TurnoCierre.MEDIODIA
        desde = datetime.combine(fecha_caja, time(10, 0, 0), tzinfo=momento.tzinfo)
        hasta = datetime.combine(fecha_caja, time(16, 59, 59), tzinfo=momento.tzinfo)
    else:
        fecha_caja = momento.date()
        turno = TurnoCierre.NOCHE
        desde = datetime.combine(fecha_caja, time(17, 0, 0), tzinfo=momento.tzinfo)
        hasta = datetime.combine(fecha_caja + timedelta(days=1), time(4, 59, 59), tzinfo=momento.tzinfo)

    return turno, fecha_caja, desde, hasta


def ventana_para_turno(fecha: date, turno: TurnoCierre) -> tuple[datetime, datetime]:
    """Calcula el rango [desde, hasta] para una fecha y turno específicos."""
    if turno == TurnoCierre.MEDIODIA:
        desde = datetime.combine(fecha, time(10, 0, 0))
        hasta = datetime.combine(fecha, time(16, 59, 59))
    else:
        desde = datetime.combine(fecha, time(17, 0, 0))
        hasta = datetime.combine(fecha + timedelta(days=1), time(4, 59, 59))
    return desde, hasta
