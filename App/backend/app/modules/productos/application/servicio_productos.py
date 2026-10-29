"""Casos de uso del catalogo."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.productos.domain.entidades import (
    CambioProducto,
    CambioReceta,
    DatosProducto,
    validar_producto,
    validar_recetas_variantes,
)
from app.modules.productos.domain.imagenes import validar_imagen_producto
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


def _validar_extras(datos) -> None:
    if datos.extras is None:
        return
    ids = [e.ingrediente_id for e in datos.extras]
    if len(ids) != len(set(ids)) or not set(ids) <= {i.ingrediente_id for i in datos.ingredientes}:
        raise DatosInvalidos("Los extras deben ser ingredientes unicos de la receta")
    for extra in datos.extras:
        if (
            not extra.precio.is_finite()
            or extra.precio <= 0
            or not extra.cantidad_requerida.is_finite()
            or extra.cantidad_requerida <= 0
            or isinstance(extra.max_por_item, bool)
            or not 1 <= extra.max_por_item <= 50
        ):
            raise DatosInvalidos("El precio, porcion o maximo del extra no son validos")


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
    async def obtener_edicion(self, producto_id: int, *, bloquear: bool = False) -> dict | None: ...
    async def categoria_edicion(self, categoria_id: int) -> dict | None: ...
    async def nombre_en_uso(self, categoria_id: int, nombre: str, excepto_id: int) -> bool: ...
    async def ingredientes_edicion(self, ids: list[int]) -> list[dict]: ...
    async def guardar_producto(self, producto_id: int, datos: CambioProducto) -> dict: ...


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
        _validar_extras(datos)
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

    async def obtener_edicion(self, producto_id: int) -> dict:
        """Consulta un producto completo manteniendo su identidad comercial."""
        fila = await self.repo.obtener_edicion(producto_id)
        if fila is None:
            raise NoEncontrado("El producto no existe")
        return fila

    async def actualizar(self, producto_id: int, cambio: CambioProducto) -> dict:
        """Guarda un reemplazo integral sobre la versión bloqueada del producto."""
        try:
            datos = validar_producto(cambio.producto)
            datos = replace(datos, imagen_url=validar_imagen_producto(datos.imagen_url))
        except ValueError as exc:
            raise DatosInvalidos(str(exc)) from exc
        _validar_extras(datos)
        actual = await self.repo.obtener_edicion(producto_id, bloquear=True)
        if actual is None:
            raise NoEncontrado("El producto no existe")
        if actual["actualizado_en"] != cambio.actualizado_en_esperado:
            raise ReglaDeNegocio("El producto fue modificado; recargalo antes de guardar")
        categoria = await self.repo.categoria_edicion(datos.categoria_id)
        historica_inactiva = datos.categoria_id == actual["categoria_id"] and (
            not datos.activo or actual["activo"]
        )
        if categoria is None or not categoria["activa"] and not historica_inactiva:
            raise DatosInvalidos("La categoria no existe o esta inactiva")
        if categoria["nombre"].strip().casefold() == "dips extra" and datos.extras:
            raise DatosInvalidos("Dips Extra no admite ingredientes extra")
        if await self.repo.nombre_en_uso(datos.categoria_id, datos.nombre, producto_id):
            raise ReglaDeNegocio("Ya existe un producto con ese nombre en la categoria")
        await self._validar_ingredientes_edicion(actual, datos)
        return await self.repo.guardar_producto(producto_id, replace(cambio, producto=datos))

    async def _validar_ingredientes_edicion(self, actual: dict, datos: DatosProducto) -> None:
        """Los insumos inactivos sólo pueden conservar sus relaciones históricas."""
        estados = await self.repo.ingredientes_edicion(
            [i.ingrediente_id for i in datos.ingredientes]
        )
        por_id = {i["id"]: i["activo"] for i in estados}
        if set(por_id) != {i.ingrediente_id for i in datos.ingredientes}:
            raise DatosInvalidos("La receta contiene ingredientes inexistentes")
        previas = {None: actual["ingredientes"]} | {
            v["nombre"]: v["ingredientes"] for v in actual["variantes"]
        }
        nuevas = [(None, datos.ingredientes)] + [
            (v.nombre, v.ingredientes) for v in datos.variantes
        ]
        for variante, ingredientes in nuevas:
            historicos = {i["ingrediente_id"]: i for i in previas.get(variante, [])}
            for ingrediente in ingredientes:
                if por_id[ingrediente.ingrediente_id]:
                    continue
                anterior = historicos.get(ingrediente.ingrediente_id)
                if anterior is None or (
                    ingrediente.cantidad_requerida != anterior["cantidad_requerida"]
                    or ingrediente.es_base != anterior["es_base"]
                ):
                    raise DatosInvalidos(
                        "Un ingrediente inactivo solo puede conservar su receta historica"
                    )
        extras_previos = {e["ingrediente_id"]: e for e in actual["extras"]}
        for extra in datos.extras:
            if por_id[extra.ingrediente_id]:
                continue
            anterior = extras_previos.get(extra.ingrediente_id)
            if anterior is None or (
                extra.cantidad_requerida != anterior["cantidad_requerida"]
                or extra.max_por_item != anterior["max_por_item"]
            ):
                raise DatosInvalidos("No se puede habilitar nueva demanda de un extra inactivo")

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
        _validar_extras(datos)
        return await self.repo.guardar_receta(producto_id, datos)
