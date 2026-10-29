"""Contratos HTTP de productos."""

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.productos.domain.entidades import (
    CambioProducto,
    CambioReceta,
    DatosProducto,
    ExtraProducto,
    IngredienteProducto,
    VarianteProducto,
    VarianteReceta,
    validar_recetas_variantes,
)
from app.modules.productos.domain.imagenes import validar_imagen_producto


class IngredienteProductoEntrada(BaseModel):
    """Ingrediente de una receta con su cantidad requerida."""

    model_config = ConfigDict(extra="forbid")

    ingrediente_id: int = Field(gt=0)
    cantidad_requerida: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    es_base: bool = True


class VarianteRecetaEntrada(BaseModel):
    """Receta de una variante identificada por su nombre."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=60)
    ingredientes: list[IngredienteProductoEntrada] = Field(min_length=1)

    @field_validator("nombre")
    @classmethod
    def normalizar_nombre(cls, valor: str) -> str:
        """Recorta espacios y exige un nombre de variante no vacío."""
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre de la variante es obligatorio")
        return valor


class VarianteProductoEntrada(VarianteRecetaEntrada):
    """Variante nueva de un producto, con precio propio y receta."""

    precio: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


def _ingredientes_dominio(
    items: list[IngredienteProductoEntrada],
) -> tuple[IngredienteProducto, ...]:
    """Convierte los ingredientes recibidos en entidades del dominio."""
    return tuple(IngredienteProducto(**item.model_dump()) for item in items)


def _validar_recetas(datos):
    """Aplica las reglas de dominio de recetas al esquema recibido y lo devuelve."""
    validar_recetas_variantes(
        _ingredientes_dominio(datos.ingredientes),
        tuple(
            VarianteReceta(v.nombre, _ingredientes_dominio(v.ingredientes)) for v in datos.variantes
        ),
    )
    return datos


class ExtraProductoEntrada(BaseModel):
    """Configuración de venta de una porción adicional, separada del costo del insumo."""

    model_config = ConfigDict(extra="forbid")
    ingrediente_id: int = Field(gt=0, strict=True)
    cantidad_requerida: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    precio: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    max_por_item: int = Field(gt=0, le=50, strict=True)


class ProductoCrear(BaseModel):
    """Datos para dar de alta un producto del catálogo con receta y variantes."""

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
    extras: list[ExtraProductoEntrada] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validar_recetas(self):
        """Valida receta base y variantes con las reglas del dominio."""
        return _validar_recetas(self)

    def a_dominio(self) -> DatosProducto:
        """Convierte la entrada HTTP en ``DatosProducto`` del dominio."""
        return DatosProducto(
            **self.model_dump(exclude={"ingredientes", "variantes", "extras"}),
            extras=tuple(ExtraProducto(**e.model_dump()) for e in self.extras),
            ingredientes=_ingredientes_dominio(self.ingredientes),
            variantes=tuple(
                VarianteProducto(v.nombre, v.precio, _ingredientes_dominio(v.ingredientes))
                for v in self.variantes
            ),
        )


class ProductoActualizar(ProductoCrear):
    """Reemplazo completo de los datos editables con control de concurrencia."""

    actualizado_en_esperado: AwareDatetime
    descripcion: str | None = Field(default=None, max_length=5000)
    orden: int = Field(default=0, ge=0, le=2147483647, strict=True)

    @field_validator("imagen_url")
    @classmethod
    def validar_imagen(cls, valor: str | None) -> str | None:
        """Excluye contenido activo y limita el tamaño de raster embebido."""
        return validar_imagen_producto(valor)

    def a_dominio(self) -> CambioProducto:
        """Convierte el reemplazo HTTP a datos y versión del dominio."""
        datos = ProductoCrear(**self.model_dump(exclude={"actualizado_en_esperado"}))
        return CambioProducto(self.actualizado_en_esperado, datos.a_dominio())


class RecetaActualizar(BaseModel):
    """Nueva receta de un producto con la marca de tiempo esperada (concurrencia)."""

    model_config = ConfigDict(extra="forbid")

    actualizado_en_esperado: AwareDatetime
    ingredientes: list[IngredienteProductoEntrada] = Field(min_length=1)
    variantes: list[VarianteRecetaEntrada] = Field(default_factory=list, max_length=10)
    extras: list[ExtraProductoEntrada] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validar_recetas(self):
        """Valida receta base y variantes con las reglas del dominio."""
        return _validar_recetas(self)

    def a_dominio(self) -> CambioReceta:
        """Convierte la entrada HTTP en ``CambioReceta`` del dominio."""
        return CambioReceta(
            self.actualizado_en_esperado,
            _ingredientes_dominio(self.ingredientes),
            tuple(
                VarianteReceta(v.nombre, _ingredientes_dominio(v.ingredientes))
                for v in self.variantes
            ),
            tuple(ExtraProducto(**e.model_dump()) for e in self.extras)
            if self.extras is not None
            else None,
        )


class IngredienteRecetaSalida(BaseModel):
    """Ingrediente de una receta con su nombre, unidad y cantidad."""

    ingrediente_id: int
    nombre: str
    unidad_medida: str
    cantidad_requerida: Decimal
    es_base: bool


class VarianteRecetaSalida(BaseModel):
    """Variante con su precio, receta e indicador de receta propia configurada."""

    nombre: str
    precio: Decimal
    ingredientes: list[IngredienteRecetaSalida]
    receta_configurada: bool


class RecetaSalida(BaseModel):
    """Receta completa de un producto: base y variantes."""

    producto_id: int
    actualizado_en: datetime
    ingredientes: list[IngredienteRecetaSalida]
    variantes: list[VarianteRecetaSalida]
    extras: list[ExtraProductoEntrada] = Field(default_factory=list)


class CategoriaEdicionSalida(BaseModel):
    """Categoría disponible para el editor; incluye la actual aunque esté inactiva."""

    id: int
    nombre: str
    activa: bool


class ProductoEdicionSalida(RecetaSalida):
    """Datos comerciales, receta y opciones que se editan en una sola transacción."""

    categoria_id: int
    categoria: str
    nombre: str
    descripcion: str | None
    precio_base: Decimal
    imagen_url: str | None
    activo: bool
    orden: int
    categorias: list[CategoriaEdicionSalida]


class VarianteProductoSalida(BaseModel):
    """Variante vendible con su precio y disponibilidad según stock."""

    nombre: str
    precio: Decimal
    disponible: bool = True
    # Unidades que alcanza el stock actual (tope 50); el pedido se revalida en el servidor.
    max_unidades: int | None = None


class ProductoSalida(BaseModel):
    """Producto del catálogo tal como lo ven el menú y el panel."""

    id: int
    categoria_id: int
    categoria: str
    nombre: str
    descripcion: str | None
    precio_base: Decimal
    imagen_url: str | None
    variantes: list[VarianteProductoSalida] = Field(default_factory=list)
    ingredientes_quitables: list[str] = Field(default_factory=list)
    extras_disponibles: list[dict] = Field(default_factory=list)
    activo: bool
    disponible: bool
    max_unidades: int | None = None


class EstadoProductoEntrada(BaseModel):
    """Activación o desactivación de un producto."""

    activo: bool
