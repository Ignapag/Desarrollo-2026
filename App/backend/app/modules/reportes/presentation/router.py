"""Endpoints de dashboard, ventas y rentabilidad."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.modules.reportes.presentation.dependencias import ServicioReportesDep
from app.modules.reportes.presentation.esquemas import (
    DashboardAdministrador,
    DashboardDuenio,
    RentabilidadEstimada,
    VentaAdministrador,
    VentaDuenio,
)
from app.modules.usuarios.presentation.dependencias import AdministradorODuenio, SoloDuenio

router = APIRouter(prefix="/api/reportes", tags=["reportes"])


@router.get("/dashboard", response_model=DashboardAdministrador | DashboardDuenio)
async def dashboard(
    fecha_desde: date,
    fecha_hasta: date,
    sesion: AdministradorODuenio,
    servicio: ServicioReportesDep,
) -> DashboardAdministrador | DashboardDuenio:
    datos = await servicio.dashboard(
        rol=sesion.rol.value, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    esquema = DashboardDuenio if sesion.rol.value == "DUENIO" else DashboardAdministrador
    return esquema(**datos)


@router.get("/ventas", response_model=list[VentaAdministrador | VentaDuenio])
async def ventas(
    fecha_desde: date,
    fecha_hasta: date,
    agrupacion: str,
    sesion: AdministradorODuenio,
    servicio: ServicioReportesDep,
    categoria_id: int | None = Query(default=None, gt=0),
    producto_id: int | None = Query(default=None, gt=0),
) -> list[VentaAdministrador | VentaDuenio]:
    filas = await servicio.ventas(
        rol=sesion.rol.value,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        agrupacion=agrupacion,
        categoria_id=categoria_id,
        producto_id=producto_id,
    )
    esquema = VentaDuenio if sesion.rol.value == "DUENIO" else VentaAdministrador
    return [esquema(**fila) for fila in filas]


@router.get("/rentabilidad", response_model=list[RentabilidadEstimada])
async def rentabilidad(
    fecha_desde: date,
    fecha_hasta: date,
    _sesion: SoloDuenio,
    servicio: ServicioReportesDep,
    categoria_id: int | None = Query(default=None, gt=0),
    producto_id: int | None = Query(default=None, gt=0),
) -> list[RentabilidadEstimada]:
    filas = await servicio.rentabilidad_estimada(
        rol="DUENIO",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        categoria_id=categoria_id,
        producto_id=producto_id,
    )
    return [RentabilidadEstimada(**fila) for fila in filas]
