"""Endpoints protegidos para arqueo, consolidacion y cierres de caja."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status

from app.core.dependencias import IpCliente
from app.modules.pagos.presentation.dependencias import ServicioCajaDep
from app.modules.pagos.domain.entidades import EstadoCierre, TurnoCierre
from app.modules.pagos.presentation.esquemas import (
    AprobarCierreEntrada,
    CierreCajaSalida,
    ConsolidadoTurnoSalida,
    GenerarCierreEntrada,
)
from app.modules.usuarios.presentation.dependencias import (
    AdministradorODuenio,
    PersonalInterno,
)

router = APIRouter(prefix="/api/caja", tags=["caja"])


@router.get(
    "/turnos/actual/consolidado",
    response_model=ConsolidadoTurnoSalida,
    summary="Consolidar ingresos del turno activo actual",
)
async def consolidar_turno_actual(
    _sesion: PersonalInterno,
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
    _sesion: PersonalInterno,
    servicio: ServicioCajaDep,
    fecha: date = Query(..., description="Fecha contable del turno (YYYY-MM-DD)"),
    turno: TurnoCierre = Query(..., description="Turno a consolidar (MEDIODIA o NOCHE)"),
) -> ConsolidadoTurnoSalida:
    """Devuelve los acumulados y desglose de cobros para una fecha y turno determinados."""
    consolidado = await servicio.consolidar_turno(fecha=fecha, turno=turno)
    return ConsolidadoTurnoSalida.desde_dominio(consolidado)


@router.post(
    "/cierres/generar",
    response_model=CierreCajaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Generar resumen de cierre de caja (automatizado o manual)",
)
async def generar_cierre(
    sesion: PersonalInterno,
    servicio: ServicioCajaDep,
    datos: GenerarCierreEntrada | None = None,
    ip: IpCliente = None,
) -> CierreCajaSalida:
    """Genera formalmente el cierre de caja para el turno, asentándolo en estado PENDIENTE_APROBACION.

    - Totaliza ingresos en efectivo, billeteras y devoluciones.
    - Vincula en lote todos los pagos del período con el cierre generado (`pago.cierre_caja_id`).
    - Si el cierre ya existía y fue aprobado, bloquea la operación.
    - Deja registro en la auditoría del sistema (RNF-09).
    """
    entrada = datos or GenerarCierreEntrada()
    cierre = await servicio.generar_resumen_cierre(
        fecha=entrada.fecha,
        turno=entrada.turno,
        generado_por=entrada.generado_por or sesion.usuario_id,
        observaciones=entrada.observaciones,
        ip_cliente=ip,
    )
    return CierreCajaSalida.desde_dominio(cierre)


@router.get(
    "/cierres",
    response_model=list[CierreCajaSalida],
    summary="Listar cierres de caja",
)
async def listar_cierres(
    _sesion: PersonalInterno,
    servicio: ServicioCajaDep,
    desde: date | None = Query(default=None, description="Filtrar desde fecha"),
    hasta: date | None = Query(default=None, description="Filtrar hasta fecha"),
    estado: EstadoCierre | None = Query(default=None, description="Filtrar por estado del cierre"),
) -> list[CierreCajaSalida]:
    """Retorna el historial de cierres de caja registrados en el sistema."""
    cierres = await servicio.listar_cierres(
        desde_fecha=desde,
        hasta_fecha=hasta,
        estado=estado,
    )
    return [CierreCajaSalida.desde_dominio(c) for c in cierres]


@router.get(
    "/cierres/{cierre_id}",
    response_model=CierreCajaSalida,
    summary="Obtener detalle de un cierre de caja",
)
async def obtener_cierre(
    cierre_id: int,
    _sesion: PersonalInterno,
    servicio: ServicioCajaDep,
) -> CierreCajaSalida:
    """Recupera el detalle completo de un cierre de caja por su identificador primario."""
    cierre = await servicio.obtener_cierre(cierre_id)
    return CierreCajaSalida.desde_dominio(cierre)


@router.post(
    "/cierres/{cierre_id}/aprobar",
    response_model=CierreCajaSalida,
    summary="Aprobar y bloquear formalmente un cierre de caja",
)
async def aprobar_cierre(
    cierre_id: int,
    datos: AprobarCierreEntrada,
    sesion: AdministradorODuenio,
    servicio: ServicioCajaDep,
    ip: IpCliente = None,
) -> CierreCajaSalida:
    """Aprueba un cierre de caja pendiente, cambiando su estado a APROBADO e inalterable (RF del alcance)."""
    cierre = await servicio.aprobar_y_bloquear_cierre(
        cierre_id=cierre_id,
        aprobado_por=datos.aprobado_por or sesion.usuario_id,
        observaciones=datos.observaciones,
        ip_cliente=ip,
    )
    return CierreCajaSalida.desde_dominio(cierre)

