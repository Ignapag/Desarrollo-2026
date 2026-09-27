"""Endpoints del catalogo de productos."""

from fastapi import APIRouter, status

from app.modules.productos.domain.entidades import DatosProducto, IngredienteProducto
from app.modules.productos.presentation.dependencias import ServicioProductosDep
from app.modules.productos.presentation.esquemas import (
    EstadoProductoEntrada,
    ProductoCrear,
    ProductoSalida,
)
from app.modules.usuarios.presentation.dependencias import AdministradorODuenio

router = APIRouter(prefix="/api/productos", tags=["productos"])


@router.get("", response_model=list[ProductoSalida])
async def listar_productos(
    servicio: ServicioProductosDep, solo_activos: bool = True
) -> list[ProductoSalida]:
    return [ProductoSalida(**fila) for fila in await servicio.listar(solo_activos=solo_activos)]


@router.post("", response_model=ProductoSalida, status_code=status.HTTP_201_CREATED)
async def crear_producto(
    datos: ProductoCrear,
    _sesion: AdministradorODuenio,
    servicio: ServicioProductosDep,
) -> ProductoSalida:
    payload = datos.model_dump(exclude={"ingredientes"})
    fila = await servicio.crear(
        DatosProducto(
            **payload,
            ingredientes=tuple(
                IngredienteProducto(**item.model_dump()) for item in datos.ingredientes
            ),
        )
    )
    return ProductoSalida(**fila)


@router.patch("/{producto_id}/estado", response_model=ProductoSalida)
async def cambiar_estado_producto(
    producto_id: int,
    datos: EstadoProductoEntrada,
    _sesion: AdministradorODuenio,
    servicio: ServicioProductosDep,
) -> ProductoSalida:
    return ProductoSalida(
        **await servicio.cambiar_estado(producto_id, activo=datos.activo)
    )
