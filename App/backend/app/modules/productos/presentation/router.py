"""Endpoints del catalogo de productos."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.modules.productos.presentation.dependencias import ServicioProductosDep
from app.modules.productos.presentation.esquemas import (
    EstadoProductoEntrada,
    ProductoCrear,
    ProductoSalida,
    RecetaActualizar,
    RecetaSalida,
)
from app.modules.usuarios.domain.entidades import ClaimsSesion
from app.modules.usuarios.presentation.dependencias import requiere_permiso

PermisoProductosGestionar = Annotated[
    ClaimsSesion, Depends(requiere_permiso("productos", "gestionar"))
]
PermisoProductosVerReceta = Annotated[
    ClaimsSesion, Depends(requiere_permiso("productos", "ver_receta"))
]

router = APIRouter(prefix="/api/productos", tags=["productos"])


@router.get("", response_model=list[ProductoSalida])
async def listar_productos(
    servicio: ServicioProductosDep, solo_activos: bool = True
) -> list[ProductoSalida]:
    return [ProductoSalida(**fila) for fila in await servicio.listar(solo_activos=solo_activos)]


@router.post("", response_model=ProductoSalida, status_code=status.HTTP_201_CREATED)
async def crear_producto(
    datos: ProductoCrear,
    _sesion: PermisoProductosGestionar,
    servicio: ServicioProductosDep,
) -> ProductoSalida:
    fila = await servicio.crear(datos.a_dominio())
    return ProductoSalida(**fila)


@router.get("/{producto_id}/receta", response_model=RecetaSalida)
async def obtener_receta(
    producto_id: int,
    _sesion: PermisoProductosVerReceta,
    servicio: ServicioProductosDep,
) -> RecetaSalida:
    return RecetaSalida(**await servicio.obtener_receta(producto_id))


@router.put("/{producto_id}/receta", response_model=RecetaSalida)
async def actualizar_receta(
    producto_id: int,
    datos: RecetaActualizar,
    _sesion: PermisoProductosGestionar,
    servicio: ServicioProductosDep,
) -> RecetaSalida:
    return RecetaSalida(**await servicio.actualizar_receta(producto_id, datos.a_dominio()))


@router.patch("/{producto_id}/estado", response_model=ProductoSalida)
async def cambiar_estado_producto(
    producto_id: int,
    datos: EstadoProductoEntrada,
    _sesion: PermisoProductosGestionar,
    servicio: ServicioProductosDep,
) -> ProductoSalida:
    return ProductoSalida(**await servicio.cambiar_estado(producto_id, activo=datos.activo))
