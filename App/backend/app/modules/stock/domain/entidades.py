"""Validaciones y niveles del inventario, independientes de la base y la API."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

UNIDADES = frozenset({"KG", "GR", "LT", "ML", "UNIDAD"})
NIVELES = frozenset({"NORMAL", "BAJO_UMBRAL", "SIN_STOCK"})
TIPOS_MOVIMIENTO = frozenset({"CONSUMO", "REPOSICION", "AJUSTE", "DEVOLUCION", "MERMA"})


@dataclass(frozen=True, slots=True)
class DatosIngrediente:
    nombre: str
    unidad_medida: str
    cantidad_actual: Decimal
    umbral_minimo: Decimal
    costo_unitario: Decimal = Decimal("0")
    dias_reposicion: tuple[str, ...] = ()
    responsable_id: int | None = None
    activo: bool = True


@dataclass(frozen=True, slots=True)
class ItemConsumoStock:
    producto_id: int
    cantidad: int
    opciones: tuple[object, ...] = ()


def validar_ingrediente(datos: DatosIngrediente) -> DatosIngrediente:
    nombre = datos.nombre.strip() if isinstance(datos.nombre, str) else ""
    if not nombre:
        raise ValueError("El nombre es obligatorio")
    if datos.unidad_medida not in UNIDADES:
        raise ValueError("La unidad de medida no es valida")
    if (
        not isinstance(datos.cantidad_actual, Decimal)
        or not datos.cantidad_actual.is_finite()
        or datos.cantidad_actual < 0
    ):
        raise ValueError("La cantidad inicial debe ser mayor o igual a cero")
    if (
        not isinstance(datos.umbral_minimo, Decimal)
        or not datos.umbral_minimo.is_finite()
        or datos.umbral_minimo <= 0
    ):
        raise ValueError("El umbral minimo debe ser mayor que cero")
    if (
        not isinstance(datos.costo_unitario, Decimal)
        or not datos.costo_unitario.is_finite()
        or datos.costo_unitario < 0
    ):
        raise ValueError("El costo unitario debe ser mayor o igual a cero")
    if datos.responsable_id is not None and datos.responsable_id <= 0:
        raise ValueError("El responsable no es valido")
    return DatosIngrediente(
        nombre,
        datos.unidad_medida,
        datos.cantidad_actual,
        datos.umbral_minimo,
        datos.costo_unitario,
        datos.dias_reposicion,
        datos.responsable_id,
        datos.activo,
    )


def validar_reposicion(cantidad: Decimal) -> None:
    if not isinstance(cantidad, Decimal) or not cantidad.is_finite() or cantidad <= 0:
        raise ValueError("La cantidad recibida debe ser mayor que cero")


def nivel_stock(cantidad: Decimal, umbral: Decimal) -> str:
    if cantidad == 0:
        return "SIN_STOCK"
    if cantidad <= umbral:
        return "BAJO_UMBRAL"
    return "NORMAL"
