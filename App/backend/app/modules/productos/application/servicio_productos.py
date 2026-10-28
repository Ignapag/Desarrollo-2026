"""Casos de uso del catalogo."""

from __future__ import annotations

from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.productos.domain.entidades import (
    CambioReceta,
    DatosProducto,
    validar_producto,
    validar_recetas_variantes,
)
from app.modules.stock.application.servicio_stock import INGREDIENTES_QUITABLES


def _con_personalizaciones(fila: dict) -> dict:
    """Agrega al producto los ingredientes de su receta que el cliente puede quitar.

    Reemplaza la lista interna ``ingredientes_receta`` por ``ingredientes_quitables``.
    """
    producto = dict(fila)
    receta = producto.pop("ingredientes_receta", [])
    producto["ingredientes_quitables"] = [
        nombre for nombre in receta if nombre.casefold() in INGREDIENTES_QUITABLES
    ]
    return producto


class RepositorioProductos(Protocol):
    """Puerto de persistencia del catálogo que implementa el repositorio SQL."""

    async def listar(self, *, solo_activos: bool) -> list[dict]: ...
    async def categoria_existe(self, categoria_id: int) -> bool: ...
    async def nombre_existe(self, categoria_id: int, nombre: str) -> bool: ...
    async def ingredientes_validos(self, ids: list[int]) -> bool: ...
    async def crear(self, datos: DatosProducto) -> dict: ...
    async def cambiar_estado(self, producto_id: int, activo: bool) -> dict | None: ...
    async def obtener_receta(self, producto_id: int, *, bloquear: bool = False) -> dict | None: ...
    async def guardar_receta(self, producto_id: int, datos: CambioReceta) -> dict: ...


class ServicioProductos:
    """Casos de uso del catálogo: listado, alta, activación y edición de recetas."""

    def __init__(self, repo: RepositorioProductos) -> None:
        """Recibe el repositorio del catálogo."""
        self.repo = repo

    async def listar(self, *, solo_activos: bool = True) -> list[dict]:
        """Lista productos (solo activos por defecto) con sus ingredientes quitables."""
        filas = await self.repo.listar(solo_activos=solo_activos)
        return [_con_personalizaciones(p) for p in filas]

    async def crear(self, datos: DatosProducto) -> dict:
        """Valida y crea un producto con su receta y variantes.

        Exige categoría activa, nombre único dentro de la categoría e ingredientes existentes y
        activos.
        """
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
        return _con_personalizaciones(await self.repo.crear(datos))

    async def cambiar_estado(self, producto_id: int, *, activo: bool) -> dict:
        """Activa o desactiva un producto del catálogo."""
        fila = await self.repo.cambiar_estado(producto_id, activo)
        if fila is None:
            raise NoEncontrado("El producto no existe")
        return _con_personalizaciones(fila)

    async def obtener_receta(self, producto_id: int) -> dict:
        """Devuelve la receta base y por variante de un producto."""
        fila = await self.repo.obtener_receta(producto_id)
        if fila is None:
            raise NoEncontrado("El producto no existe")
        return fila

    async def actualizar_receta(self, producto_id: int, datos: CambioReceta) -> dict:
        """Reemplaza la receta de un producto con control de concurrencia optimista.

        Falla si la receta cambió desde que se leyó (``actualizado_en``) o si se alteran las
        variantes existentes o su orden.
        """
        try:
            validar_recetas_variantes(datos.ingredientes, datos.variantes)
        except ValueError as exc:
            raise DatosInvalidos(str(exc)) from exc
        # Bloquea el producto para que dos ediciones simultáneas de la receta no se pisen.
        actual = await self.repo.obtener_receta(producto_id, bloquear=True)
        if actual is None:
            raise NoEncontrado("El producto no existe")
        if actual["actualizado_en"] != datos.actualizado_en_esperado:
            raise ReglaDeNegocio("La receta fue modificada; recargala antes de guardar")
        if [v.nombre for v in datos.variantes] != [v["nombre"] for v in actual["variantes"]]:
            raise DatosInvalidos("Deben conservarse las variantes actuales y su orden")
        if not await self.repo.ingredientes_validos([i.ingrediente_id for i in datos.ingredientes]):
            raise DatosInvalidos("La receta contiene ingredientes inexistentes o inactivos")
        return await self.repo.guardar_receta(producto_id, datos)
