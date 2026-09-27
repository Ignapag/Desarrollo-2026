"""Pruebas unitarias para la consolidación de ingresos y turnos de caja."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.pagos.application.servicio_caja import ServicioCaja
from app.modules.pagos.domain.entidades import (
    CierreCaja,
    EstadoCierre,
    MetodoPago,
    TotalesMetodoPago,
    TurnoCierre,
    determinar_turno_y_ventana,
    ventana_para_turno,
)
from app.modules.pagos.infrastructure.repositorio_caja_sql import RepositorioCajaSQL


# ---------------------------------------------------------------------------
# Pruebas de reglas de dominio: turnos y ventanas horarias
# ---------------------------------------------------------------------------

def test_determinar_turno_mediodia():
    """A las 13:30 el sistema debe asignar el turno MEDIODIA del mismo día."""
    momento = datetime(2026, 7, 15, 13, 30, 0)
    turno, fecha_caja, desde, hasta = determinar_turno_y_ventana(momento)

    assert turno == TurnoCierre.MEDIODIA
    assert fecha_caja == date(2026, 7, 15)
    assert desde == datetime(2026, 7, 15, 10, 0, 0)
    assert hasta == datetime(2026, 7, 15, 16, 59, 59)


def test_determinar_turno_noche_antes_de_medianoche():
    """A las 21:00 el sistema debe asignar el turno NOCHE de la fecha actual."""
    momento = datetime(2026, 7, 15, 21, 0, 0)
    turno, fecha_caja, desde, hasta = determinar_turno_y_ventana(momento)

    assert turno == TurnoCierre.NOCHE
    assert fecha_caja == date(2026, 7, 15)
    assert desde == datetime(2026, 7, 15, 17, 0, 0)
    assert hasta == datetime(2026, 7, 16, 4, 59, 59)


def test_determinar_turno_noche_despues_de_medianoche():
    """A las 01:30 AM el turno corresponde a la NOCHE del día anterior."""
    momento = datetime(2026, 7, 16, 1, 30, 0)
    turno, fecha_caja, desde, hasta = determinar_turno_y_ventana(momento)

    assert turno == TurnoCierre.NOCHE
    assert fecha_caja == date(2026, 7, 15)  # Fecha contable del turno nocturno
    assert desde == datetime(2026, 7, 15, 17, 0, 0)
    assert hasta == datetime(2026, 7, 16, 4, 59, 59)


def test_ventana_para_turno_especifico():
    """Calcula correctamente las ventanas para fechas y turnos históricos."""
    f = date(2026, 8, 1)
    desde_m, hasta_m = ventana_para_turno(f, TurnoCierre.MEDIODIA)
    assert desde_m == datetime(2026, 8, 1, 10, 0, 0)
    assert hasta_m == datetime(2026, 8, 1, 16, 59, 59)

    desde_n, hasta_n = ventana_para_turno(f, TurnoCierre.NOCHE)
    assert desde_n == datetime(2026, 8, 1, 17, 0, 0)
    assert hasta_n == datetime(2026, 8, 2, 4, 59, 59)


def test_cierre_aprobado_es_inalterable():
    """Un cierre con estado APROBADO lanza ReglaDeNegocio si se intenta alterar."""
    cierre = CierreCaja(
        id=1,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        abierto_en=datetime(2026, 7, 15, 17, 0, 0),
        cerrado_en=datetime(2026, 7, 16, 2, 0, 0),
        total_efectivo=Decimal("50000.00"),
        total_billeteras=Decimal("80000.00"),
        total_devoluciones=Decimal("0.00"),
        total_general=Decimal("130000.00"),
        cantidad_pedidos=45,
        estado=EstadoCierre.APROBADO,
        generado_por=1,
        aprobado_por=2,
        aprobado_en=datetime(2026, 7, 16, 2, 30, 0),
        observaciones="Cierre sin diferencias",
    )
    with pytest.raises(ReglaDeNegocio, match="inalterable"):
        cierre.validar_inmutabilidad()


# ---------------------------------------------------------------------------
# Pruebas del servicio de aplicación: ServicioCaja
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidar_turno_calculo_completo():
    """El servicio consolida totales de efectivo, billeteras y devoluciones."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)

    mock_repo.consolidar_totales_turno.return_value = {
        "total_efectivo": Decimal("45000.00"),
        "total_billeteras": Decimal("95000.00"),
        "total_devoluciones": Decimal("5000.00"),
        "total_general": Decimal("135000.00"),  # 45000 + 95000 - 5000
        "total_propinas": Decimal("8200.00"),
        "cantidad_pedidos": 38,
        "cantidad_pagos": 42,
        "pagos_pendientes_conciliacion": 2,
    }
    mock_repo.desglose_por_metodo.return_value = [
        TotalesMetodoPago(metodo_pago=MetodoPago.MERCADO_PAGO, total=Decimal("60000.00"), cantidad=20),
        TotalesMetodoPago(metodo_pago=MetodoPago.EFECTIVO, total=Decimal("45000.00"), cantidad=15),
        TotalesMetodoPago(metodo_pago=MetodoPago.CUENTA_DNI, total=Decimal("35000.00"), cantidad=7),
    ]

    servicio = ServicioCaja(mock_uow, mock_repo)
    resultado = await servicio.consolidar_turno(
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.MEDIODIA,
    )

    assert resultado.fecha == date(2026, 7, 15)
    assert resultado.turno == TurnoCierre.MEDIODIA
    assert resultado.total_efectivo == Decimal("45000.00")
    assert resultado.total_billeteras == Decimal("95000.00")
    assert resultado.total_devoluciones == Decimal("5000.00")
    assert resultado.total_general == Decimal("135000.00")
    assert resultado.total_propinas == Decimal("8200.00")
    assert resultado.cantidad_pedidos == 38
    assert resultado.pagos_pendientes_conciliacion == 2
    assert len(resultado.desglose_metodos) == 3
    assert resultado.desglose_metodos[0].metodo_pago == MetodoPago.MERCADO_PAGO


@pytest.mark.asyncio
async def test_generar_resumen_cierre_exitoso():
    """Genera el registro formal de cierre en estado PENDIENTE_APROBACION y vincula pagos."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)

    mock_repo.obtener_cierre_por_fecha_turno.return_value = None
    mock_repo.consolidar_totales_turno.return_value = {
        "total_efectivo": Decimal("30000.00"),
        "total_billeteras": Decimal("50000.00"),
        "total_devoluciones": Decimal("2000.00"),
        "total_general": Decimal("78000.00"),
        "total_propinas": Decimal("4000.00"),
        "cantidad_pedidos": 25,
        "cantidad_pagos": 27,
        "pagos_pendientes_conciliacion": 0,
    }

    cierre_creado = CierreCaja(
        id=10,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        abierto_en=datetime(2026, 7, 15, 17, 0, 0),
        cerrado_en=datetime(2026, 7, 16, 2, 0, 0),
        total_efectivo=Decimal("30000.00"),
        total_billeteras=Decimal("50000.00"),
        total_devoluciones=Decimal("2000.00"),
        total_general=Decimal("78000.00"),
        cantidad_pedidos=25,
        estado=EstadoCierre.PENDIENTE_APROBACION,
        generado_por=1,
        aprobado_por=None,
        aprobado_en=None,
        observaciones="Cierre turno noche normal",
    )
    mock_repo.crear_o_actualizar_cierre.return_value = cierre_creado
    mock_repo.vincular_pagos_al_cierre.return_value = 27

    servicio = ServicioCaja(mock_uow, mock_repo)
    resultado = await servicio.generar_resumen_cierre(
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        generado_por=1,
        observaciones="Cierre turno noche normal",
    )

    assert resultado.id == 10
    assert resultado.estado == EstadoCierre.PENDIENTE_APROBACION
    assert resultado.total_general == Decimal("78000.00")
    mock_repo.vincular_pagos_al_cierre.assert_called_once()
    mock_repo.crear_o_actualizar_cierre.assert_called_once()


@pytest.mark.asyncio
async def test_generar_resumen_cierre_falla_si_ya_aprobado():
    """No permite regenerar o reabrir un turno que ya fue aprobado formalmente."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)

    cierre_aprobado = CierreCaja(
        id=10,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.MEDIODIA,
        abierto_en=datetime(2026, 7, 15, 10, 0, 0),
        cerrado_en=datetime(2026, 7, 15, 16, 30, 0),
        total_efectivo=Decimal("20000.00"),
        total_billeteras=Decimal("30000.00"),
        total_devoluciones=Decimal("0.00"),
        total_general=Decimal("50000.00"),
        cantidad_pedidos=15,
        estado=EstadoCierre.APROBADO,
        generado_por=1,
        aprobado_por=2,
        aprobado_en=datetime(2026, 7, 15, 17, 0, 0),
        observaciones="Aprobado por el dueño",
    )
    mock_repo.obtener_cierre_por_fecha_turno.return_value = cierre_aprobado

    servicio = ServicioCaja(mock_uow, mock_repo)
    with pytest.raises(ReglaDeNegocio, match="ya fue aprobado y no puede reabrirse"):
        await servicio.generar_resumen_cierre(
            fecha=date(2026, 7, 15),
            turno=TurnoCierre.MEDIODIA,
        )


@pytest.mark.asyncio
async def test_obtener_cierre_no_encontrado():
    """Lanza NoEncontrado cuando se solicita un cierre inexistente."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)
    mock_repo.obtener_cierre_por_id.return_value = None

    servicio = ServicioCaja(mock_uow, mock_repo)
    with pytest.raises(NoEncontrado, match="no encontrado"):
        await servicio.obtener_cierre(999)


@pytest.mark.asyncio
async def test_aprobar_y_bloquear_cierre_exitoso():
    """Aprueba un cierre pendiente fijando timestamp y responsable."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)

    cierre_pendiente = CierreCaja(
        id=5,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        abierto_en=datetime(2026, 7, 15, 17, 0, 0),
        cerrado_en=datetime(2026, 7, 16, 2, 0, 0),
        total_efectivo=Decimal("40000.00"),
        total_billeteras=Decimal("60000.00"),
        total_devoluciones=Decimal("0.00"),
        total_general=Decimal("100000.00"),
        cantidad_pedidos=30,
        estado=EstadoCierre.PENDIENTE_APROBACION,
        generado_por=1,
        aprobado_por=None,
        aprobado_en=None,
        observaciones=None,
    )
    cierre_aprobado = CierreCaja(
        id=5,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        abierto_en=datetime(2026, 7, 15, 17, 0, 0),
        cerrado_en=datetime(2026, 7, 16, 2, 0, 0),
        total_efectivo=Decimal("40000.00"),
        total_billeteras=Decimal("60000.00"),
        total_devoluciones=Decimal("0.00"),
        total_general=Decimal("100000.00"),
        cantidad_pedidos=30,
        estado=EstadoCierre.APROBADO,
        generado_por=1,
        aprobado_por=2,
        aprobado_en=datetime(2026, 7, 16, 2, 30, 0),
        observaciones="Cierre aprobado sin discrepancias",
    )

    mock_repo.obtener_cierre_por_id.return_value = cierre_pendiente
    mock_repo.aprobar_cierre.return_value = cierre_aprobado

    servicio = ServicioCaja(mock_uow, mock_repo)
    resultado = await servicio.aprobar_y_bloquear_cierre(
        cierre_id=5,
        aprobado_por=2,
        observaciones="Cierre aprobado sin discrepancias",
    )

    assert resultado.id == 5
    assert resultado.estado == EstadoCierre.APROBADO
    assert resultado.aprobado_por == 2
    assert resultado.es_aprobado
    mock_repo.aprobar_cierre.assert_called_once_with(
        cierre_id=5,
        aprobado_por=2,
        observaciones="Cierre aprobado sin discrepancias",
    )


@pytest.mark.asyncio
async def test_aprobar_cierre_ya_aprobado_falla():
    """No permite volver a aprobar un cierre que ya se encuentra en estado APROBADO."""
    mock_uow = AsyncMock()
    mock_repo = AsyncMock(spec=RepositorioCajaSQL)

    cierre_ya_aprobado = CierreCaja(
        id=5,
        fecha=date(2026, 7, 15),
        turno=TurnoCierre.NOCHE,
        abierto_en=datetime(2026, 7, 15, 17, 0, 0),
        cerrado_en=datetime(2026, 7, 16, 2, 0, 0),
        total_efectivo=Decimal("40000.00"),
        total_billeteras=Decimal("60000.00"),
        total_devoluciones=Decimal("0.00"),
        total_general=Decimal("100000.00"),
        cantidad_pedidos=30,
        estado=EstadoCierre.APROBADO,
        generado_por=1,
        aprobado_por=2,
        aprobado_en=datetime(2026, 7, 16, 2, 30, 0),
        observaciones=None,
    )
    mock_repo.obtener_cierre_por_id.return_value = cierre_ya_aprobado

    servicio = ServicioCaja(mock_uow, mock_repo)
    with pytest.raises(ReglaDeNegocio, match="ya fue aprobado previamente y es inalterable"):
        await servicio.aprobar_y_bloquear_cierre(
            cierre_id=5,
            aprobado_por=2,
        )

