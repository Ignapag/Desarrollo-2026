"""Entidades y reglas puras del catalogo."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class IngredienteProducto:
    ingrediente_id: int
    cantidad_requerida: Decimal
    es_base: bool = True


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


def validar_producto(datos: DatosProducto) -> DatosProducto:
    if datos.categoria_id <= 0:
        raise ValueError("La categoria no es valida")
    if not datos.nombre.strip():
        raise ValueError("El nombre es obligatorio")
    if datos.precio_base <= 0:
        raise ValueError("El precio debe ser mayor a cero")
    if datos.orden < 0:
        raise ValueError("El orden no puede ser negativo")
    if not datos.ingredientes:
        raise ValueError("El producto debe tener al menos un ingrediente en su receta")
    ids: set[int] = set()
    for ingrediente in datos.ingredientes:
        if ingrediente.ingrediente_id <= 0 or ingrediente.cantidad_requerida <= 0:
            raise ValueError("Los ingredientes y cantidades de la receta deben ser validos")
        if ingrediente.ingrediente_id in ids:
            raise ValueError("No se puede repetir un ingrediente en la receta")
        ids.add(ingrediente.ingrediente_id)
    return DatosProducto(
        categoria_id=datos.categoria_id,
        nombre=datos.nombre.strip(),
        descripcion=datos.descripcion.strip() if datos.descripcion else None,
        precio_base=datos.precio_base,
        imagen_url=datos.imagen_url,
        activo=datos.activo,
        orden=datos.orden,
        ingredientes=datos.ingredientes,
    )
