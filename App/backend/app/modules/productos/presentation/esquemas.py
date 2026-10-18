"""Contratos HTTP de productos."""

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.productos.domain.entidades import (
    CambioReceta,
    DatosProducto,
    IngredienteProducto,
    VarianteProducto,
    VarianteReceta,
    validar_recetas_variantes,
)


class IngredienteProductoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingrediente_id: int = Field(gt=0)
    cantidad_requerida: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    es_base: bool = True


class VarianteRecetaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=60)
    ingredientes: list[IngredienteProductoEntrada] = Field(min_length=1)

    @field_validator("nombre")
    @classmethod
    def normalizar_nombre(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre de la variante es obligatorio")
        return valor


class VarianteProductoEntrada(VarianteRecetaEntrada):
    precio: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


def _ingredientes_dominio(
    items: list[IngredienteProductoEntrada],
) -> tuple[IngredienteProducto, ...]:
    return tuple(IngredienteProducto(**item.model_dump()) for item in items)


def _validar_recetas(datos):
    validar_recetas_variantes(
        _ingredientes_dominio(datos.ingredientes),
        tuple(
            VarianteReceta(v.nombre, _ingredientes_dominio(v.ingredientes)) for v in datos.variantes
        ),
    )
    return datos


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
    variantes: list[VarianteProductoEntrada] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validar_recetas(self):
        return _validar_recetas(self)

    def a_dominio(self) -> DatosProducto:
        return DatosProducto(
            **self.model_dump(exclude={"ingredientes", "variantes"}),
            ingredientes=_ingredientes_dominio(self.ingredientes),
            variantes=tuple(
                VarianteProducto(v.nombre, v.precio, _ingredientes_dominio(v.ingredientes))
                for v in self.variantes
            ),
        )


class RecetaActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actualizado_en_esperado: AwareDatetime
    ingredientes: list[IngredienteProductoEntrada] = Field(min_length=1)
    variantes: list[VarianteRecetaEntrada] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validar_recetas(self):
        return _validar_recetas(self)

    def a_dominio(self) -> CambioReceta:
        return CambioReceta(
            self.actualizado_en_esperado,
            _ingredientes_dominio(self.ingredientes),
            tuple(
                VarianteReceta(v.nombre, _ingredientes_dominio(v.ingredientes))
                for v in self.variantes
            ),
        )


class IngredienteRecetaSalida(BaseModel):
    ingrediente_id: int
    nombre: str
    unidad_medida: str
    cantidad_requerida: Decimal
    es_base: bool


class VarianteRecetaSalida(BaseModel):
    nombre: str
    precio: Decimal
    ingredientes: list[IngredienteRecetaSalida]
    receta_configurada: bool


class RecetaSalida(BaseModel):
    producto_id: int
    actualizado_en: datetime
    ingredientes: list[IngredienteRecetaSalida]
    variantes: list[VarianteRecetaSalida]


class VarianteProductoSalida(BaseModel):
    nombre: str
    precio: Decimal
    disponible: bool = True


class ProductoSalida(BaseModel):
    id: int
    categoria_id: int
    categoria: str
    nombre: str
    descripcion: str | None
    precio_base: Decimal
    imagen_url: str | None
    variantes: list[VarianteProductoSalida] = Field(default_factory=list)
    ingredientes_quitables: list[str] = Field(default_factory=list)
    activo: bool
    disponible: bool


class EstadoProductoEntrada(BaseModel):
    activo: bool
