"""Entidades y reglas puras del catalogo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IngredienteProducto:
    ingrediente_id: int
    cantidad_requerida: Decimal
    es_base: bool = True


@dataclass(frozen=True, slots=True)
class VarianteProducto:
    nombre: str
    precio: Decimal
    ingredientes: tuple[IngredienteProducto, ...]


@dataclass(frozen=True, slots=True)
class VarianteReceta:
    nombre: str
    ingredientes: tuple[IngredienteProducto, ...]


@dataclass(frozen=True, slots=True)
class CambioReceta:
    actualizado_en_esperado: datetime
    ingredientes: tuple[IngredienteProducto, ...]
    variantes: tuple[VarianteReceta, ...] = ()


@dataclass(frozen=True, slots=True)
class DatosProducto:
    categoria_id: int
    nombre: str
    descripcion: str | None
    precio_base: Decimal
    imagen_url: str | None = None
    activo: bool = True
    orden: int = 0
    ingredientes: tuple[IngredienteProducto, ...] = ()
    variantes: tuple[VarianteProducto, ...] = ()


def validar_receta(ingredientes: tuple[IngredienteProducto, ...]) -> None:
    if not ingredientes:
        raise ValueError("El producto debe tener al menos un ingrediente en su receta")
    ids: set[int] = set()
    for item in ingredientes:
        cantidad = item.cantidad_requerida
        if (
            item.ingrediente_id <= 0
            or not isinstance(cantidad, Decimal)
            or not cantidad.is_finite()
            or cantidad <= 0
            or cantidad > Decimal("999999999.999")
            or cantidad != cantidad.quantize(Decimal("0.001"))
        ):
            raise ValueError("Los ingredientes y cantidades de la receta deben ser validos")
        if item.ingrediente_id in ids:
            raise ValueError("No se puede repetir un ingrediente en la receta")
        ids.add(item.ingrediente_id)


def validar_recetas_variantes(
    ingredientes: tuple[IngredienteProducto, ...],
    variantes: tuple[VarianteProducto | VarianteReceta, ...],
) -> None:
    validar_receta(ingredientes)
    nombres: set[str] = set()
    base = {i.ingrediente_id: i for i in ingredientes}
    if len(variantes) > 10:
        raise ValueError("Se permiten hasta 10 variantes")
    for variante in variantes:
        nombre = variante.nombre.strip()
        if not nombre or len(nombre) > 60 or nombre.casefold() in nombres:
            raise ValueError("Los nombres de las variantes deben ser unicos y validos")
        nombres.add(nombre.casefold())
        validar_receta(variante.ingredientes)
        if set(base) != {i.ingrediente_id for i in variante.ingredientes}:
            raise ValueError("Las variantes deben usar los mismos ingredientes de la receta base")
    if variantes and base != {i.ingrediente_id: i for i in variantes[0].ingredientes}:
        raise ValueError("La receta base debe coincidir con la primera variante")


def validar_producto(datos: DatosProducto) -> DatosProducto:
    if datos.categoria_id <= 0:
        raise ValueError("La categoria no es valida")
    if not datos.nombre.strip():
        raise ValueError("El nombre es obligatorio")
    if datos.precio_base <= 0:
        raise ValueError("El precio debe ser mayor a cero")
    if datos.orden < 0:
        raise ValueError("El orden no puede ser negativo")
    validar_recetas_variantes(datos.ingredientes, datos.variantes)
    for variante in datos.variantes:
        if (
            not isinstance(variante.precio, Decimal)
            or not variante.precio.is_finite()
            or variante.precio <= 0
            or variante.precio > Decimal("9999999999.99")
            or variante.precio != variante.precio.quantize(Decimal("0.01"))
        ):
            raise ValueError("El precio de la variante no es valido")
    return replace(
        datos,
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion.strip() if datos.descripcion else None,
        variantes=tuple(replace(v, nombre=v.nombre.strip()) for v in datos.variantes),
    )
