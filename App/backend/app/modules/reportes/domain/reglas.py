"""Convenciones funcionales adoptadas para reportes."""

from __future__ import annotations

from datetime import date

from app.errores import DatosInvalidos, SinPermiso

# Una venta es un pedido confirmado que no esta cancelado. El periodo se toma
# de pedido.confirmado_en, nunca de pedido.creado_en.
ESTADOS_VENTA = (
    "CONFIRMADO",
    "EN_PREPARACION",
    "LISTO",
    "EN_CAMINO",
    "ENTREGADO",
)
ROLES_REPORTES = frozenset({"DUENIO", "ADMINISTRADOR"})
AGRUPACIONES = {"DIA": "day", "SEMANA": "week", "MES": "month"}
ZONA_NEGOCIO = "America/Argentina/Buenos_Aires"


def validar_rol(rol: str, *, financiero: bool = False, autorizado: bool | None = None) -> None:
    permitido = rol in ROLES_REPORTES and (not financiero or rol == "DUENIO")
    if not (permitido if autorizado is None else autorizado):
        raise SinPermiso("No tiene permiso para consultar este reporte")


def validar_periodo(desde: date, hasta: date) -> None:
    if desde is None or hasta is None or desde > hasta:
        raise DatosInvalidos("El rango de fechas no es valido")


def validar_agrupacion(agrupacion: str) -> str:
    if agrupacion not in AGRUPACIONES:
        raise DatosInvalidos("La agrupacion no es valida; TEMPORADA esta pendiente de definicion")
    return AGRUPACIONES[agrupacion]
