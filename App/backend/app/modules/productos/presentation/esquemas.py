"""Contratos HTTP de productos."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class IngredienteProductoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingrediente_id: int = Field(gt=0)
    cantidad_requerida: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    es_base: bool = True


class ProductoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria_id: int = Field(gt=0)
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str | None = None
    precio_base: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    imagen_url: str | None = None
    activo: bool = True
    orden: int = Field(default=0, ge=0)
    ingredientes: list[IngredienteProductoEntrada] = Field(min_length=1)


class VarianteProductoSalida(BaseModel):
    nombre: str
    precio: Decimal


class ProductoSalida(BaseModel):
    id: int
    categoria_id: int
    categoria: str
    nombre: str
    descripcion: str | None
    precio_base: Decimal
    imagen_url: str | None
    variantes: list[VarianteProductoSalida] = Field(default_factory=list)
    activo: bool
    disponible: bool


class EstadoProductoEntrada(BaseModel):
    activo: bool
