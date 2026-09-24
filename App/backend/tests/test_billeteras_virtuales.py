"""Pruebas unitarias para la integración de billeteras virtuales (Mercado Pago)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.application.servicio_pagos import ServicioPagos
from app.modules.pagos.domain.entidades import (
    EstadoPago,
    MetodoPago,
    Pago,
    TipoPago,
)
from app.modules.pagos.infrastructure.cliente_billetera import (
    ClienteMercadoPago,
    DetallePagoExterno,
    PreferenciaCobro,
)


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.ejecutar = AsyncMock(return_value=1)
    return uow


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_cliente_mp():
    cliente = AsyncMock(spec=ClienteMercadoPago)
    cliente.crear_preferencia = AsyncMock(
        return_value=PreferenciaCobro(
            preference_id="pref_test_123",
            init_point="https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref_test_123",
            qr_data="00020101021243650016com.mercadopago_test",
            monto=Decimal("8500.00"),
            referencia_externa="pedido_10_12345",
        )
    )
    cliente.consultar_pago = AsyncMock(
        return_value=DetallePagoExterno(
            payment_id="pay_999888",
            status="approved",
            status_detail="accredited",
            monto=Decimal("8500.00"),
            referencia_externa="pref_test_123",
        )
    )
    return cliente


@pytest.mark.asyncio
async def test_cliente_mercadopago_modo_simulacion():
    """El cliente en modo simulación (sin token de producción) genera links y QR válidos."""
    cliente = ClienteMercadoPago(access_token=None)
    pref = await cliente.crear_preferencia(
        pedido_id=1,
        numero_pedido=1001,
        monto=Decimal("6000.00"),
        descripcion="Monu Burger - Pedido #1001",
    )
    assert pref.preference_id.startswith("pref_")
    assert "mercadopago" in pref.init_point
    assert len(pref.qr_data) > 10

    detalle = await cliente.consultar_pago("sim_123")
    assert detalle.status == "approved"

    detalle_rechazado = await cliente.consultar_pago("rechazado_456")
    assert detalle_rechazado.status == "rejected"


@pytest.mark.asyncio
async def test_iniciar_cobro_digital_exitoso(mock_uow, mock_repo, mock_cliente_mp):
    """Inicia la orden digital en Mercado Pago y genera el pago PENDIENTE."""
    mock_repo.obtener_pedido_para_actualizar.return_value = {
        "id": 10,
        "numero": 1010,
        "total": Decimal("8500.00"),
        "estado": "PENDIENTE",
    }
    mock_repo.total_pagado_por_pedido.return_value = Decimal("0.00")

    pago_esperado = Pago(
        id=50,
        pedido_id=10,
        cierre_caja_id=None,
        tipo=TipoPago.COBRO,
        metodo_pago=MetodoPago.MERCADO_PAGO,
        monto=Decimal("8500.00"),
        propina=Decimal("0.00"),
        estado=EstadoPago.PENDIENTE,
        referencia_externa="pref_test_123",
        registrado_por=1,
        registrado_en=None,  # type: ignore[arg-type]
        conciliado_en=None,
        motivo=None,
    )
    mock_repo.registrar_pago.return_value = pago_esperado

    servicio = ServicioPagos(mock_uow, mock_repo, cliente_mp=mock_cliente_mp)
    resultado = await servicio.iniciar_cobro_digital(
        pedido_id=10,
        metodo_pago=MetodoPago.MERCADO_PAGO,
        registrado_por=1,
    )

    assert resultado.pago.id == 50
    assert resultado.pago.estado == EstadoPago.PENDIENTE
    assert resultado.preferencia.preference_id == "pref_test_123"
    assert "mercadopago" in resultado.preferencia.init_point
    mock_repo.registrar_pago.assert_called_once()


@pytest.mark.asyncio
async def test_iniciar_cobro_digital_rechaza_efectivo(mock_uow, mock_repo, mock_cliente_mp):
    """No permite iniciar cobro digital con método EFECTIVO."""
    servicio = ServicioPagos(mock_uow, mock_repo, cliente_mp=mock_cliente_mp)
    with pytest.raises(DatosInvalidos, match="cobro en efectivo debe utilizar el endpoint"):
        await servicio.iniciar_cobro_digital(
            pedido_id=10,
            metodo_pago=MetodoPago.EFECTIVO,
        )


@pytest.mark.asyncio
async def test_iniciar_cobro_digital_pedido_ya_saldado(mock_uow, mock_repo, mock_cliente_mp):
    """Rechaza iniciar cobro si el pedido ya está totalmente pagado."""
    mock_repo.obtener_pedido_para_actualizar.return_value = {
        "id": 10,
        "numero": 1010,
        "total": Decimal("5000.00"),
        "estado": "CONFIRMADO",
    }
    mock_repo.total_pagado_por_pedido.return_value = Decimal("5000.00")

    servicio = ServicioPagos(mock_uow, mock_repo, cliente_mp=mock_cliente_mp)
    with pytest.raises(ReglaDeNegocio, match="totalmente"):
        await servicio.iniciar_cobro_digital(
            pedido_id=10,
            metodo_pago=MetodoPago.MERCADO_PAGO,
        )


@pytest.mark.asyncio
async def test_webhook_mercadopago_pago_aprobado(mock_uow, mock_repo, mock_cliente_mp):
    """El webhook procesa la acreditación de Mercado Pago y concilia el pago."""
    pago_pendiente = Pago(
        id=50,
        pedido_id=10,
        cierre_caja_id=None,
        tipo=TipoPago.COBRO,
        metodo_pago=MetodoPago.MERCADO_PAGO,
        monto=Decimal("8500.00"),
        propina=Decimal("0.00"),
        estado=EstadoPago.PENDIENTE,
        referencia_externa="pref_test_123",
        registrado_por=1,
        registrado_en=None,  # type: ignore[arg-type]
        conciliado_en=None,
        motivo=None,
    )
    mock_repo.obtener_pago_por_referencia.return_value = pago_pendiente
    mock_repo.obtener_pedido_para_actualizar.return_value = {
        "id": 10,
        "numero": 1010,
        "total": Decimal("8500.00"),
        "estado": "PENDIENTE",
    }
    mock_repo.total_pagado_por_pedido.return_value = Decimal("8500.00")

    servicio = ServicioPagos(mock_uow, mock_repo, cliente_mp=mock_cliente_mp)
    respuesta = await servicio.procesar_webhook_mercadopago(payment_id="pay_999888")

    assert respuesta["estado"] == "aprobado"
    assert respuesta["pago_id"] == 50
    mock_repo.actualizar_pago_por_referencia.assert_called_once()
    mock_repo.cambiar_estado_pedido.assert_called_once_with(
        pedido_id=10,
        estado="CONFIRMADO",
        usuario_id=1,
        observacion="Pago digital aprobado (MP #pay_999888)",
    )


@pytest.mark.asyncio
async def test_webhook_mercadopago_idempotente(mock_uow, mock_repo, mock_cliente_mp):
    """Si el pago ya figura como CONCILIADO, el webhook no vuelve a procesar."""
    pago_conciliado = Pago(
        id=50,
        pedido_id=10,
        cierre_caja_id=None,
        tipo=TipoPago.COBRO,
        metodo_pago=MetodoPago.MERCADO_PAGO,
        monto=Decimal("8500.00"),
        propina=Decimal("0.00"),
        estado=EstadoPago.CONCILIADO,
        referencia_externa="pref_test_123",
        registrado_por=1,
        registrado_en=None,  # type: ignore[arg-type]
        conciliado_en=None,
        motivo=None,
    )
    mock_repo.obtener_pago_por_referencia.return_value = pago_conciliado

    servicio = ServicioPagos(mock_uow, mock_repo, cliente_mp=mock_cliente_mp)
    respuesta = await servicio.procesar_webhook_mercadopago(payment_id="pay_999888")

    assert respuesta["estado"] == "ya_conciliado"
    mock_repo.actualizar_pago_por_referencia.assert_not_called()
    mock_repo.cambiar_estado_pedido.assert_not_called()
