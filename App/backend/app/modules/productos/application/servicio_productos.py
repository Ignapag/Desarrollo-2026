"""Casos de uso del catalogo."""

from __future__ import annotations

from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.productos.domain.entidades import DatosProducto, validar_producto


class RepositorioProductos(Protocol):
    async def listar(self, *, solo_activos: bool) -> list[dict]: ...
    async def categoria_existe(self, categoria_id: int) -> bool: ...
    async def nombre_existe(self, categoria_id: int, nombre: str) -> bool: ...
    async def ingredientes_validos(self, ids: list[int]) -> bool: ...
    async def crear(self, datos: DatosProducto) -> dict: ...
    async def cambiar_estado(self, producto_id: int, activo: bool) -> dict | None: ...


class ServicioProductos:
    def __init__(self, repo: RepositorioProductos) -> None:
        self.repo = repo

    async def listar(self, *, solo_activos: bool = True) -> list[dict]:
        return await self.repo.listar(solo_activos=solo_activos)

    async def crear(self, datos: DatosProducto) -> dict:
        try:
            datos = validar_producto(datos)
        except ValueError as exc:
            raise DatosInvalidos(str(exc)) from exc
        if not await self.repo.categoria_existe(datos.categoria_id):
            raise DatosInvalidos("La categoria no existe o esta inactiva")
        if await self.repo.nombre_existe(datos.categoria_id, datos.nombre):
            raise ReglaDeNegocio("Ya existe un producto con ese nombre en la categoria")
        if not await self.repo.ingredientes_validos(
            [item.ingrediente_id for item in datos.ingredientes]
        ):
            raise DatosInvalidos("La receta contiene ingredientes inexistentes o inactivos")
        return await self.repo.crear(datos)

    async def cambiar_estado(self, producto_id: int, *, activo: bool) -> dict:
        fila = await self.repo.cambiar_estado(producto_id, activo)
        if fila is None:
            raise NoEncontrado("El producto no existe")
        return fila
