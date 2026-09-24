"""Endpoints de la API para arqueo, consolidación y cierres de caja.

⚠️ PENDIENTE DE PROTECCIÓN: Al igual que en delivery, la guarda de autenticación
y rol del módulo de Usuarios y Seguridad (EDT 1.8) se agregará antes del parámetro
`servicio` cuando esté integrada (Rol: DUEÑO / ADMINISTRADOR / EMPLEADO).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.core.dependencias import ServicioCajaDep
from app.modules.pagos.domain.entidades import TurnoCierre
from app.modules.pagos.presentation.esquemas import ConsolidadoTurnoSalida

router = APIRouter(prefix="/api/caja", tags=["caja"])


@router.get(
    "/turnos/actual/consolidado",
    response_model=ConsolidadoTurnoSalida,
    summary="Consolidar ingresos del turno activo actual",
)
async def consolidar_turno_actual(
    servicio: ServicioCajaDep,
) -> ConsolidadoTurnoSalida:
    """Calcula y consolida en tiempo real los ingresos, egresos y desglose por método

    del turno activo en curso (detectado automáticamente según la hora del sistema).
    """
    consolidado = await servicio.consolidar_turno()
    return ConsolidadoTurnoSalida.desde_dominio(consolidado)


@router.get(
    "/turnos/consolidado",
    response_model=ConsolidadoTurnoSalida,
    summary="Consolidar ingresos de una fecha y turno específico",
)
async def consolidar_turno_especifico(
    fecha: date = Query(..., description="Fecha contable del turno (YYYY-MM-DD)"),
    turno: TurnoCierre = Query(..., description="Turno a consolidar (MEDIODIA o NOCHE)"),
    servicio: ServicioCajaDep = None,  # type: ignore[assignment]
) -> ConsolidadoTurnoSalida:
    """Devuelve los acumulados y desglose de cobros para una fecha y turno determinados."""
    consolidado = await servicio.consolidar_turno(fecha=fecha, turno=turno)
    return ConsolidadoTurnoSalida.desde_dominio(consolidado)
