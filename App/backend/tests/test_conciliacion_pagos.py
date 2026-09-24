"""Pruebas unitarias para el servicio de conciliación de pagos, devoluciones y anulaciones."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.pagos.application.servicio_conciliacion import ServicioConciliacion
from app.modules.pagos.domain.entidades import (
    EstadoPago,
    MetodoPago,
    Pago,
    TipoPago,
)


def _crear_pago_ejemplo(
    pago_id: int = 1,
    pedido_id: int = 10,
    monto: Decimal = Decimal("5000.00"),
    propina: Decimal = Decimal("0.00"),
    estado: EstadoPago = EstadoPago.PENDIENTE,
    tipo: TipoPago = TipoPago.COBRO,
    metodo: MetodoPago = MetodoPago.TRANSFERENCIA,
    referencia_externa: str | None = "TRANSF-001",
) -> Pago:
    return Pago(
        id=pago_id,
        pedido_id=pedido_id,
        cierre_caja_id=None,
        tipo=tipo,
        metodo_pago=metodo,
        monto=monto,
        propina=propina,
        estado=estado,
        referencia_externa=referencia_externa,
        registrado_por=1,
        registrado_en=datetime.now(timezone.utc),
        conciliado_en=datetime.now(timezone.utc) if estado == EstadoPago.CONCILIADO else None,
        motivo=None,
    )


@pytest.fixture
def mock_uow():
    uow = AsyncMock()
    uow.ejecutar = AsyncMock(return_value=1)
    return uow


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def servicio(mock_uow, mock_repo) -> ServicioConciliacion:
    return ServicioConciliacion(uow=mock_uow, repo=mock_repo)


# =========================================================================
# Conciliación Individual
# =========================================================================


@pytest.mark.asyncio
async def test_conciliar_pago_inexistente_lanza_no_encontrado(servicio, mock_repo):
    mock_repo.obtener_pago_por_id.return_value = None

    with pytest.raises(NoEncontrado, match="no encontrado"):
        await servicio.conciliar_pago(pago_id=999)


@pytest.mark.asyncio
async def test_conciliar_pago_ya_conciliado_es_idempotente(servicio, mock_repo):
    pago_conciliado = _crear_pago_ejemplo(pago_id=1, estado=EstadoPago.CONCILIADO)
    mock_repo.obtener_pago_por_id.return_value = pago_conciliado

    resultado = await servicio.conciliar_pago(pago_id=1)

    assert resultado.id == 1
    assert resultado.es_conciliado is True
    mock_repo.conciliar_pago.assert_not_called()


@pytest.mark.asyncio
async def test_conciliar_pago_anulado_lanza_regla_de_negocio(servicio, mock_repo):
    pago_anulado = _crear_pago_ejemplo(pago_id=2, estado=EstadoPago.ANULADO)
    mock_repo.obtener_pago_por_id.return_value = pago_anulado

    with pytest.raises(ReglaDeNegocio, match="está anulado"):
        await servicio.conciliar_pago(pago_id=2)


@pytest.mark.asyncio
async def test_conciliar_pago_exitoso_y_confirma_pedido_saldado(servicio, mock_repo, mock_uow):
    pago_pendiente = _crear_pago_ejemplo(pago_id=3, pedido_id=15, monto=Decimal("5000.00"))
    pago_conciliado = _crear_pago_ejemplo(pago_id=3, pedido_id=15, monto=Decimal("5000.00"), estado=EstadoPago.CONCILIADO)

    mock_repo.obtener_pago_por_id.return_value = pago_pendiente
    mock_repo.conciliar_pago.return_value = pago_conciliado
    mock_repo.obtener_pedido_para_actualizar.return_value = {
        "id": 15,
        "total": Decimal("5000.00"),
        "estado": "PENDIENTE",
    }
    mock_repo.total_pagado_por_pedido.return_value = Decimal("5000.00")

    resultado = await servicio.conciliar_pago(
        pago_id=3,
        conciliar_por=2,
        comprobante="BANCO-REC-777",
        ip_cliente="127.0.0.1",
    )

    assert resultado.estado == EstadoPago.CONCILIADO
    mock_repo.conciliar_pago.assert_awaited_once_with(3, "BANCO-REC-777")
    mock_repo.cambiar_estado_pedido.assert_awaited_once_with(
        pedido_id=15,
        estado="CONFIRMADO",
        usuario_id=2,
        observacion="Pago #3 conciliado y pedido saldado",
    )


@pytest.mark.asyncio
async def test_conciliar_pago_parcial_no_confirma_pedido_si_falta_saldo(servicio, mock_repo):
    pago_pendiente = _crear_pago_ejemplo(pago_id=4, pedido_id=20, monto=Decimal("2000.00"))
    pago_conciliado = _crear_pago_ejemplo(pago_id=4, pedido_id=20, monto=Decimal("2000.00"), estado=EstadoPago.CONCILIADO)

    mock_repo.obtener_pago_por_id.return_value = pago_pendiente
    mock_repo.conciliar_pago.return_value = pago_conciliado
    mock_repo.obtener_pedido_para_actualizar.return_value = {
        "id": 20,
        "total": Decimal("5000.00"),
        "estado": "PENDIENTE",
    }
    # Solo se cubrieron 2000 de los 5000
    mock_repo.total_pagado_por_pedido.return_value = Decimal("2000.00")

    resultado = await servicio.conciliar_pago(pago_id=4)

    assert resultado.estado == EstadoPago.CONCILIADO
    mock_repo.cambiar_estado_pedido.assert_not_called()


# =========================================================================
# Conciliación en Lote
# =========================================================================


@pytest.mark.asyncio
async def test_conciliar_lote_procesa_exitosos_y_captura_fallidos(servicio, mock_repo):
    pago_1 = _crear_pago_ejemplo(pago_id=10, estado=EstadoPago.PENDIENTE)
    pago_1_conc = _crear_pago_ejemplo(pago_id=10, estado=EstadoPago.CONCILIADO)

    async def _obtener_pago(pid):
        if pid == 10:
            return pago_1
        return None  # pid 11 no existe

    mock_repo.obtener_pago_por_id.side_effect = _obtener_pago
    mock_repo.conciliar_pago.return_value = pago_1_conc
    mock_repo.obtener_pedido_para_actualizar.return_value = None

    resultado = await servicio.conciliar_lote(pago_ids=[10, 11], conciliar_por=1)

    assert resultado["total_procesados"] == 1
    assert 10 in resultado["conciliados"]
    assert len(resultado["fallidos"]) == 1
    assert resultado["fallidos"][0]["pago_id"] == 11


# =========================================================================
# Registro de Devoluciones (Egresos C-11)
# =========================================================================


@pytest.mark.asyncio
async def test_registrar_devolucion_valida_motivo_obligatorio(servicio):
    with pytest.raises(DatosInvalidos, match="motivo de la devolución es obligatorio"):
        await servicio.registrar_devolucion(
            pedido_id=1,
            monto=Decimal("1000.00"),
            motivo="   ",
        )


@pytest.mark.asyncio
async def test_registrar_devolucion_valida_monto_positivo(servicio):
    with pytest.raises(DatosInvalidos, match="mayor a cero"):
        await servicio.registrar_devolucion(
            pedido_id=1,
            monto=Decimal("0.00"),
            motivo="Error de cobro",
        )


@pytest.mark.asyncio
async def test_registrar_devolucion_pedido_inexistente(servicio, mock_repo):
    mock_repo.obtener_pedido_para_actualizar.return_value = None

    with pytest.raises(NoEncontrado, match="no encontrado"):
        await servicio.registrar_devolucion(
            pedido_id=99,
            monto=Decimal("500.00"),
            motivo="Cliente canceló",
        )


@pytest.mark.asyncio
async def test_registrar_devolucion_rechaza_monto_superior_a_lo_pagado(servicio, mock_repo):
    mock_repo.obtener_pedido_para_actualizar.return_value = {"id": 1, "total": Decimal("4000.00")}
    # El cliente solo pagó 2000 neto
    mock_repo.total_pagado_por_pedido.return_value = Decimal("2000.00")

    with pytest.raises(DatosInvalidos, match="supera el total neto abonado"):
        await servicio.registrar_devolucion(
            pedido_id=1,
            monto=Decimal("2500.00"),
            motivo="Reintegro total solicitado por error",
        )


@pytest.mark.asyncio
async def test_registrar_devolucion_exitosa(servicio, mock_repo):
    mock_repo.obtener_pedido_para_actualizar.return_value = {"id": 1, "total": Decimal("5000.00")}
    mock_repo.total_pagado_por_pedido.return_value = Decimal("5000.00")

    devolucion_creada = _crear_pago_ejemplo(
        pago_id=50,
        pedido_id=1,
        monto=Decimal("1500.00"),
        tipo=TipoPago.DEVOLUCION,
        estado=EstadoPago.CONCILIADO,
    )
    mock_repo.registrar_pago.return_value = devolucion_creada

    resultado = await servicio.registrar_devolucion(
        pedido_id=1,
        monto=Decimal("1500.00"),
        motivo="Falta de stock de bebida",
        metodo_pago=MetodoPago.EFECTIVO,
        registrado_por=3,
        ip_cliente="192.168.1.10",
    )

    assert resultado.id == 50
    assert resultado.tipo == TipoPago.DEVOLUCION
    assert resultado.estado == EstadoPago.CONCILIADO
    mock_repo.registrar_pago.assert_awaited_once_with(
        pedido_id=1,
        tipo=TipoPago.DEVOLUCION,
        metodo_pago=MetodoPago.EFECTIVO,
        monto=Decimal("1500.00"),
        propina=Decimal("0.00"),
        estado=EstadoPago.CONCILIADO,
        referencia_externa=None,
        registrado_por=3,
        conciliado_en=None,
        motivo="Falta de stock de bebida",
    )


# =========================================================================
# Anulación de Pagos
# =========================================================================


@pytest.mark.asyncio
async def test_anular_pago_valida_motivo_obligatorio(servicio):
    with pytest.raises(DatosInvalidos, match="motivo de anulación es obligatorio"):
        await servicio.anular_pago(pago_id=1, motivo="")


@pytest.mark.asyncio
async def test_anular_pago_inexistente(servicio, mock_repo):
    mock_repo.obtener_pago_por_id.return_value = None

    with pytest.raises(NoEncontrado, match="no encontrado"):
        await servicio.anular_pago(pago_id=99, motivo="Cargado duplicado")


@pytest.mark.asyncio
async def test_anular_pago_ya_conciliado_rechaza(servicio, mock_repo):
    pago_conciliado = _crear_pago_ejemplo(pago_id=1, estado=EstadoPago.CONCILIADO)
    mock_repo.obtener_pago_por_id.return_value = pago_conciliado

    with pytest.raises(ReglaDeNegocio, match="porque ya está conciliado"):
        await servicio.anular_pago(pago_id=1, motivo="Error de carga")


@pytest.mark.asyncio
async def test_anular_pago_ya_anulado_rechaza(servicio, mock_repo):
    pago_anulado = _crear_pago_ejemplo(pago_id=2, estado=EstadoPago.ANULADO)
    mock_repo.obtener_pago_por_id.return_value = pago_anulado

    with pytest.raises(ReglaDeNegocio, match="ya se encuentra anulado"):
        await servicio.anular_pago(pago_id=2, motivo="Reintentar anulación")


@pytest.mark.asyncio
async def test_anular_pago_pendiente_exitoso(servicio, mock_repo):
    pago_pendiente = _crear_pago_ejemplo(pago_id=5, estado=EstadoPago.PENDIENTE)
    pago_anulado = _crear_pago_ejemplo(pago_id=5, estado=EstadoPago.ANULADO)

    mock_repo.obtener_pago_por_id.return_value = pago_pendiente
    mock_repo.anular_pago.return_value = pago_anulado

    resultado = await servicio.anular_pago(
        pago_id=5,
        motivo="Transferencia rechazada por el banco",
        anulado_por=1,
    )

    assert resultado.estado == EstadoPago.ANULADO
    mock_repo.anular_pago.assert_awaited_once_with(5, "Transferencia rechazada por el banco")


# =========================================================================
# Listado de Pendientes
# =========================================================================


@pytest.mark.asyncio
async def test_listar_pendientes_conciliacion(servicio, mock_repo):
    pendientes = [
        _crear_pago_ejemplo(pago_id=1, estado=EstadoPago.PENDIENTE),
        _crear_pago_ejemplo(pago_id=2, estado=EstadoPago.PENDIENTE),
    ]
    mock_repo.listar_pagos_pendientes_conciliacion.return_value = pendientes

    resultado = await servicio.listar_pendientes_conciliacion()

    assert len(resultado) == 2
    assert all(p.estado == EstadoPago.PENDIENTE for p in resultado)
