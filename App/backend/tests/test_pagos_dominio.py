"""Pruebas unitarias de dominio para el módulo de pagos y cobro en efectivo.

Lógica pura de negocio: no requiere conexión a base de datos ni servidor web.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    EstadoPago,
    MetodoPago,
    Pago,
    TipoPago,
    calcular_cobro_efectivo,
    calcular_estado_financiero,
)


def _crear_pago_ejemplo(
    id_: int = 1,
    pedido_id: int = 10,
    monto: str = "5000.00",
    propina: str = "0.00",
    metodo: MetodoPago = MetodoPago.EFECTIVO,
    estado: EstadoPago = EstadoPago.PENDIENTE,
    tipo: TipoPago = TipoPago.COBRO,
) -> Pago:
    return Pago(
        id=id_,
        pedido_id=pedido_id,
        cierre_caja_id=None,
        tipo=tipo,
        metodo_pago=metodo,
        monto=Decimal(monto),
        propina=Decimal(propina),
        estado=estado,
        referencia_externa=None,
        registrado_por=1,
        registrado_en=datetime.now(timezone.utc),
        conciliado_en=datetime.now(timezone.utc) if estado == EstadoPago.CONCILIADO else None,
        motivo=None,
    )


# ---------------------------------------------------------------------------
# Pruebas de cálculo de cobro en efectivo y vuelto
# ---------------------------------------------------------------------------

def test_pago_efectivo_monto_exacto():
    """El cliente paga con el importe exacto del pedido."""
    total = Decimal("12500.00")
    detalle = calcular_cobro_efectivo(
        total_pedido=total,
        total_ya_pagado=Decimal("0.00"),
        monto_recibido=Decimal("12500.00"),
    )
    assert detalle.monto_cobrado == Decimal("12500.00")
    assert detalle.vuelto == Decimal("0.00")
    assert detalle.saldo_restante == Decimal("0.00")
    assert detalle.propina == Decimal("0.00")


def test_pago_efectivo_con_vuelto():
    """El cliente entrega un billete mayor y se le calcula el vuelto correspondiente."""
    total = Decimal("8400.00")
    recibido = Decimal("10000.00")
    detalle = calcular_cobro_efectivo(
        total_pedido=total,
        total_ya_pagado=Decimal("0.00"),
        monto_recibido=recibido,
    )
    assert detalle.monto_cobrado == Decimal("8400.00")
    assert detalle.vuelto == Decimal("1600.00")
    assert detalle.saldo_restante == Decimal("0.00")


def test_pago_efectivo_con_propina_y_vuelto():
    """El cliente abona el pedido, deja propina y recibe el vuelto restante."""
    total = Decimal("9500.00")
    propina = Decimal("1000.00")
    recibido = Decimal("15000.00")
    detalle = calcular_cobro_efectivo(
        total_pedido=total,
        total_ya_pagado=Decimal("0.00"),
        monto_recibido=recibido,
        propina=propina,
    )
    assert detalle.monto_cobrado == Decimal("9500.00")
    assert detalle.propina == Decimal("1000.00")
    assert detalle.vuelto == Decimal("4500.00")
    assert detalle.saldo_restante == Decimal("0.00")


def test_pago_efectivo_parcial():
    """El cliente realiza un pago parcial en efectivo."""
    total = Decimal("10000.00")
    monto_a_pagar = Decimal("4000.00")
    recibido = Decimal("5000.00")

    detalle = calcular_cobro_efectivo(
        total_pedido=total,
        total_ya_pagado=Decimal("0.00"),
        monto_recibido=recibido,
        monto_a_pagar=monto_a_pagar,
    )
    assert detalle.monto_cobrado == Decimal("4000.00")
    assert detalle.vuelto == Decimal("1000.00")
    assert detalle.saldo_restante == Decimal("6000.00")


def test_pago_efectivo_segundo_pago_completa_saldo():
    """Un pedido con un cobro previo de $4000 se salda con los $6000 restantes."""
    total = Decimal("10000.00")
    ya_pagado = Decimal("4000.00")
    recibido = Decimal("6000.00")

    detalle = calcular_cobro_efectivo(
        total_pedido=total,
        total_ya_pagado=ya_pagado,
        monto_recibido=recibido,
    )
    assert detalle.monto_cobrado == Decimal("6000.00")
    assert detalle.vuelto == Decimal("0.00")
    assert detalle.saldo_restante == Decimal("0.00")


def test_error_cuando_pedido_ya_esta_totalmente_pagado():
    """No permite registrar más cobros si el pedido ya está saldado."""
    total = Decimal("5000.00")
    ya_pagado = Decimal("5000.00")

    with pytest.raises(ReglaDeNegocio, match="totalmente saldado"):
        calcular_cobro_efectivo(
            total_pedido=total,
            total_ya_pagado=ya_pagado,
            monto_recibido=Decimal("5000.00"),
        )


def test_error_cuando_dinero_recibido_no_alcanza():
    """Lanza DatosInvalidos si el dinero entregado por el cliente no cubre el importe."""
    total = Decimal("5000.00")
    recibido = Decimal("4000.00")

    with pytest.raises(DatosInvalidos, match="no alcanza"):
        calcular_cobro_efectivo(
            total_pedido=total,
            total_ya_pagado=Decimal("0.00"),
            monto_recibido=recibido,
        )


def test_error_cuando_monto_a_pagar_supera_saldo():
    """Lanza DatosInvalidos si se pretende imputar un monto superior al saldo pendiente."""
    total = Decimal("5000.00")
    with pytest.raises(DatosInvalidos, match="supera el saldo pendiente"):
        calcular_cobro_efectivo(
            total_pedido=total,
            total_ya_pagado=Decimal("0.00"),
            monto_recibido=Decimal("7000.00"),
            monto_a_pagar=Decimal("6000.00"),
        )


def test_error_monto_a_pagar_cero_o_negativo():
    """El monto a imputar debe ser estrictamente positivo."""
    total = Decimal("5000.00")
    with pytest.raises(DatosInvalidos, match="mayor a cero"):
        calcular_cobro_efectivo(
            total_pedido=total,
            total_ya_pagado=Decimal("0.00"),
            monto_recibido=Decimal("5000.00"),
            monto_a_pagar=Decimal("0.00"),
        )


def test_error_propina_negativa():
    """La propina no puede ser negativa."""
    total = Decimal("5000.00")
    with pytest.raises(DatosInvalidos, match="La propina no puede ser negativa"):
        calcular_cobro_efectivo(
            total_pedido=total,
            total_ya_pagado=Decimal("0.00"),
            monto_recibido=Decimal("6000.00"),
            propina=Decimal("-100.00"),
        )


# ---------------------------------------------------------------------------
# Pruebas de balance y estado financiero del pedido
# ---------------------------------------------------------------------------

def test_estado_financiero_sin_pagos():
    """Un pedido sin pagos tiene saldo pendiente igual al total y esta_saldado es False."""
    estado = calcular_estado_financiero(
        pedido_id=1,
        numero=1001,
        estado_pedido="PENDIENTE",
        total_pedido=Decimal("7500.00"),
        pagos=[],
    )
    assert estado.total_pagado == Decimal("0.00")
    assert estado.saldo_pendiente == Decimal("7500.00")
    assert not estado.esta_saldado
    assert estado.cantidad_pagos == 0


def test_estado_financiero_totalmente_saldado():
    """Un pedido con pago por el monto total queda marcado como saldado."""
    p1 = _crear_pago_ejemplo(id_=1, monto="7500.00")
    estado = calcular_estado_financiero(
        pedido_id=1,
        numero=1001,
        estado_pedido="CONFIRMADO",
        total_pedido=Decimal("7500.00"),
        pagos=[p1],
    )
    assert estado.total_pagado == Decimal("7500.00")
    assert estado.saldo_pendiente == Decimal("0.00")
    assert estado.esta_saldado
    assert estado.cantidad_pagos == 1


def test_estado_financiero_con_devolucion():
    """Una devolución registrada reduce el neto pagado e incrementa el saldo pendiente."""
    cobro = _crear_pago_ejemplo(id_=1, monto="10000.00", tipo=TipoPago.COBRO)
    devolucion = _crear_pago_ejemplo(id_=2, monto="3000.00", tipo=TipoPago.DEVOLUCION)

    estado = calcular_estado_financiero(
        pedido_id=1,
        numero=1001,
        estado_pedido="CONFIRMADO",
        total_pedido=Decimal("10000.00"),
        pagos=[cobro, devolucion],
    )
    # Neto = 10000 - 3000 = 7000. Saldo restante = 10000 - 7000 = 3000
    assert estado.total_pagado == Decimal("7000.00")
    assert estado.saldo_pendiente == Decimal("3000.00")
    assert not estado.esta_saldado
    assert estado.cantidad_pagos == 2


# ---------------------------------------------------------------------------
# Pruebas de inmutabilidad de pagos conciliados (alcance y triggers)
# ---------------------------------------------------------------------------

def test_pago_pendiente_permite_modificacion():
    """Un pago pendiente no lanza error al validar atributos."""
    pago = _crear_pago_ejemplo(id_=1, monto="5000.00", estado=EstadoPago.PENDIENTE)
    # No debe lanzar excepción
    pago.validar_inmutabilidad(
        nuevo_monto=Decimal("6000.00"),
        nuevo_metodo=MetodoPago.TRANSFERENCIA,
        nueva_propina=Decimal("500.00"),
        nuevo_pedido_id=10,
    )


def test_pago_conciliado_bloquea_modificacion_de_monto():
    """Un pago conciliado no permite alterar su monto (regla del alcance)."""
    pago = _crear_pago_ejemplo(id_=1, monto="5000.00", estado=EstadoPago.CONCILIADO)
    with pytest.raises(ReglaDeNegocio, match="No se puede modificar un pago ya conciliado"):
        pago.validar_inmutabilidad(
            nuevo_monto=Decimal("5500.00"),
            nuevo_metodo=MetodoPago.EFECTIVO,
            nueva_propina=Decimal("0.00"),
            nuevo_pedido_id=10,
        )


def test_pago_conciliado_bloquea_modificacion_de_metodo():
    """Un pago conciliado no permite alterar su método de pago."""
    pago = _crear_pago_ejemplo(id_=1, monto="5000.00", estado=EstadoPago.CONCILIADO)
    with pytest.raises(ReglaDeNegocio, match="No se puede modificar un pago ya conciliado"):
        pago.validar_inmutabilidad(
            nuevo_monto=Decimal("5000.00"),
            nuevo_metodo=MetodoPago.MERCADO_PAGO,
            nueva_propina=Decimal("0.00"),
            nuevo_pedido_id=10,
        )
