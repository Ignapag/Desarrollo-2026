"""Endpoints de inventario, reposicion y trazabilidad de stock."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status

from app.modules.stock.domain.entidades import DatosIngrediente
from app.modules.stock.presentation.dependencias import ServicioStockDep
from app.modules.stock.presentation.esquemas import (
    IngredienteCrear,
    IngredienteModificar,
    IngredienteSalida,
    MovimientoSalida,
    ReposicionCrear,
    ReposicionSalida,
)
from app.modules.usuarios.presentation.dependencias import PersonalInterno

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/ingredientes", response_model=list[IngredienteSalida])
async def listar_ingredientes(
    _sesion: PersonalInterno,
    servicio: ServicioStockDep,
    nombre: str | None = None,
    responsable_id: int | None = Query(default=None, gt=0),
    activo: bool | None = None,
    nivel: str | None = None,
) -> list[IngredienteSalida]:
    filas = await servicio.listar(
        nombre=nombre, responsable_id=responsable_id, activo=activo, nivel=nivel
    )
    return [IngredienteSalida(**fila) for fila in filas]


@router.post(
    "/ingredientes", response_model=IngredienteSalida, status_code=status.HTTP_201_CREATED
)
async def crear_ingrediente(
    datos: IngredienteCrear, _sesion: PersonalInterno, servicio: ServicioStockDep
) -> IngredienteSalida:
    fila = await servicio.registrar(DatosIngrediente(**datos.model_dump()))
    return IngredienteSalida(**fila)


@router.patch("/ingredientes/{ingrediente_id}", response_model=IngredienteSalida)
async def modificar_ingrediente(
    ingrediente_id: int,
    datos: IngredienteModificar,
    _sesion: PersonalInterno,
    servicio: ServicioStockDep,
) -> IngredienteSalida:
    fila = await servicio.modificar(ingrediente_id, datos.model_dump(exclude_unset=True))
    return IngredienteSalida(**fila)


@router.post("/ingredientes/{ingrediente_id}/reposiciones", response_model=ReposicionSalida)
async def reponer_ingrediente(
    ingrediente_id: int,
    datos: ReposicionCrear,
    sesion: PersonalInterno,
    servicio: ServicioStockDep,
) -> ReposicionSalida:
    fila = await servicio.reponer(
        ingrediente_id, datos.cantidad, usuario_id=sesion.usuario_id, origen=datos.origen
    )
    return ReposicionSalida(**fila)


@router.get("/movimientos", response_model=list[MovimientoSalida])
async def historial_stock(
    _sesion: PersonalInterno,
    servicio: ServicioStockDep,
    ingrediente_id: int | None = Query(default=None, gt=0),
    desde: date | None = None,
    hasta: date | None = None,
    tipo: str | None = None,
) -> list[MovimientoSalida]:
    filas = await servicio.historial(
        ingrediente_id=ingrediente_id, desde=desde, hasta=hasta, tipo=tipo
    )
    return [MovimientoSalida(**fila) for fila in filas]
