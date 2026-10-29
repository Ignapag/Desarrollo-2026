"""Endpoints de dashboard, ventas y rentabilidad."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.errores import SinPermiso
from app.modules.reportes.presentation.dependencias import ServicioReportesDep
from app.modules.reportes.presentation.esquemas import (
    DashboardAdministrador,
    DashboardDuenio,
    DirectorioClientes,
    RentabilidadEstimada,
    VentaAdministrador,
    VentaDuenio,
)
from app.modules.usuarios.domain.entidades import ClaimsSesion
from app.modules.usuarios.presentation.dependencias import requiere_permiso

# Permisos de reportes: directorio de clientes y reportes (los financieros, aparte).
PermisoClientesVer = Annotated[ClaimsSesion, Depends(requiere_permiso("clientes", "ver"))]
PermisoReportesVer = Annotated[ClaimsSesion, Depends(requiere_permiso("reportes", "ver"))]

def requiere_reportes_financieros(sesion: PermisoReportesVer) -> ClaimsSesion:
    """Dependencia que exige, además de ver reportes, el permiso financiero."""
    if not sesion.puede("reportes.financieros"):
        raise SinPermiso("No tenés permiso para consultar reportes financieros")
    return sesion


PermisoReportesFinancieros = Annotated[ClaimsSesion, Depends(requiere_reportes_financieros)]

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.get("/clientes", response_model=DirectorioClientes)
async def clientes(
    sesion: PermisoClientesVer,
    servicio: ServicioReportesDep,
    q: str | None = None,
    limite: int = Query(default=50, ge=1, le=100),
    desplazamiento: int = Query(default=0, ge=0),
    incluir_inactivos: bool = False,
) -> DirectorioClientes:
    """Directorio paginado de clientes con búsqueda por nombre o teléfono."""
    datos = await servicio.clientes(
        rol=sesion.rol.value,
        q=q,
        limite=limite,
        desplazamiento=desplazamiento,
        incluir_inactivos=incluir_inactivos,
        autorizado=sesion.puede("clientes.ver"),
    )
    return DirectorioClientes(**datos)


@router.get("/dashboard", response_model=DashboardAdministrador | DashboardDuenio)
async def dashboard(
    fecha_desde: date,
    fecha_hasta: date,
    sesion: PermisoReportesVer,
    servicio: ServicioReportesDep,
) -> DashboardAdministrador | DashboardDuenio:
    """Tablero de reportes; incluye ingresos solo con permiso financiero."""
    datos = await servicio.dashboard(
        rol=sesion.rol.value,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        autorizado=sesion.puede("reportes.ver"),
        financieros=sesion.puede("reportes.financieros"),
    )
    esquema = DashboardDuenio if sesion.puede("reportes.financieros") else DashboardAdministrador
    return esquema(**datos)


@router.get("/ventas", response_model=list[VentaAdministrador | VentaDuenio])
async def ventas(
    fecha_desde: date,
    fecha_hasta: date,
    agrupacion: str,
    sesion: PermisoReportesVer,
    servicio: ServicioReportesDep,
    categoria_id: int | None = Query(default=None, gt=0),
    producto_id: int | None = Query(default=None, gt=0),
) -> list[VentaAdministrador | VentaDuenio]:
    """Reporte de ventas agrupado por día, semana o mes, con montos según permiso."""
    filas = await servicio.ventas(
        rol=sesion.rol.value,
        autorizado=sesion.puede("reportes.ver"),
        financieros=sesion.puede("reportes.financieros"),
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        agrupacion=agrupacion,
        categoria_id=categoria_id,
        producto_id=producto_id,
    )
    esquema = VentaDuenio if sesion.puede("reportes.financieros") else VentaAdministrador
    return [esquema(**fila) for fila in filas]


@router.get("/rentabilidad", response_model=list[RentabilidadEstimada])
async def rentabilidad(
    fecha_desde: date,
    fecha_hasta: date,
    sesion: PermisoReportesFinancieros,
    servicio: ServicioReportesDep,
    categoria_id: int | None = Query(default=None, gt=0),
    producto_id: int | None = Query(default=None, gt=0),
) -> list[RentabilidadEstimada]:
    """Rentabilidad estimada por producto (requiere permiso financiero)."""
    filas = await servicio.rentabilidad_estimada(
        rol=sesion.rol.value,
        autorizado=sesion.puede("reportes.financieros"),
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        categoria_id=categoria_id,
        producto_id=producto_id,
    )
    return [RentabilidadEstimada(**fila) for fila in filas]
