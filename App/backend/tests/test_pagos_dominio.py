"""Pruebas unitarias de dominio para el módulo de pagos y cobro en efectivo.

Lógica pura de negocio: no requiere conexión a base de datos ni servidor web.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.domain.entidades import (
    calcular_cobro_efectivo,
)


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
    # Total necesario = 9500 + 1000 = 10500. Vuelto = 15000 - 10500 = 4500.
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
