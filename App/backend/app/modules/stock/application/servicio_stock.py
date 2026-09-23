"""Casos de uso de ingredientes, reposicion, historial y alertas."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.core.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.domain.entidades import (
    NIVELES,
    TIPOS_MOVIMIENTO,
    DatosIngrediente,
    validar_ingrediente,
    validar_reposicion,
)


class RepositorioStock(Protocol):
    async def listar(
        self,
        *,
        nombre: str | None,
        responsable_id: int | None,
        activo: bool | None,
        nivel: str | None,
    ) -> list[dict]: ...
    async def ingrediente(self, ingrediente_id: int, *, bloquear: bool = False) -> dict | None: ...
    async def existe_nombre(self, nombre: str, *, excepto_id: int | None = None) -> bool: ...
    async def responsable_valido(self, responsable_id: int) -> bool: ...
    async def asociado_a_producto_activo(self, ingrediente_id: int) -> bool: ...
    async def crear(self, datos: DatosIngrediente) -> dict: ...
    async def modificar(self, ingrediente_id: int, datos: DatosIngrediente) -> dict: ...
    async def reponer(
        self, ingrediente_id: int, cantidad: Decimal, *, usuario_id: int | None, origen: str
    ) -> dict: ...
    async def historial(
        self,
        *,
        ingrediente_id: int | None,
        desde: date | None,
        hasta: date | None,
        tipo: str | None,
    ) -> list[dict]: ...


class ServicioStock:
    def __init__(self, repositorio: RepositorioStock) -> None:
        self.repo = repositorio

    async def listar(
        self,
        *,
        nombre: str | None = None,
        responsable_id: int | None = None,
        activo: bool | None = None,
        nivel: str | None = None,
    ) -> list[dict]:
        if nivel is not None and nivel not in NIVELES:
            raise DatosInvalidos("El nivel de stock no es valido")
        if responsable_id is not None and responsable_id <= 0:
            raise DatosInvalidos("El responsable no es valido")
        return await self.repo.listar(
            nombre=nombre, responsable_id=responsable_id, activo=activo, nivel=nivel
        )

    async def registrar(self, datos: DatosIngrediente) -> dict:
        datos = self._validar(datos)
        await self._comprobar_referencias(datos)
        if await self.repo.existe_nombre(datos.nombre):
            raise ReglaDeNegocio("Ya existe un ingrediente con ese nombre")
        return await self.repo.crear(datos)

    async def modificar(self, ingrediente_id: int, cambios: dict) -> dict:
        permitidos = {
            "nombre",
            "unidad_medida",
            "umbral_minimo",
            "costo_unitario",
            "dias_reposicion",
            "responsable_id",
            "activo",
        }
        if set(cambios) - permitidos:
            raise DatosInvalidos("La cantidad y la fecha solo cambian mediante movimientos")
        actual = await self.repo.ingrediente(ingrediente_id)
        if actual is None:
            raise NoEncontrado("El ingrediente no existe")
        datos = self._validar(
            replace(
                DatosIngrediente(
                    nombre=actual["nombre"],
                    unidad_medida=actual["unidad_medida"],
                    cantidad_actual=actual["cantidad_actual"],
                    umbral_minimo=actual["umbral_minimo"],
                    costo_unitario=actual["costo_unitario"],
                    dias_reposicion=tuple(actual["dias_reposicion"]),
                    responsable_id=actual["responsable_id"],
                    activo=actual["activo"],
                ),
                **cambios,
            )
        )
        await self._comprobar_referencias(datos)
        if (
            actual["activo"]
            and not datos.activo
            and await self.repo.asociado_a_producto_activo(ingrediente_id)
        ):
            raise ReglaDeNegocio(
                "No se puede desactivar un ingrediente asociado a productos activos"
            )
        if await self.repo.existe_nombre(datos.nombre, excepto_id=ingrediente_id):
            raise ReglaDeNegocio("Ya existe un ingrediente con ese nombre")
        return await self.repo.modificar(ingrediente_id, datos)

    async def reponer(
        self,
        ingrediente_id: int,
        cantidad: Decimal,
        *,
        usuario_id: int | None = None,
        origen: str = "REPOSICION_MANUAL",
    ) -> dict:
        try:
            validar_reposicion(cantidad)
        except ValueError as exc:
            raise DatosInvalidos(str(exc)) from exc
        if not origen.strip():
            raise DatosInvalidos("El origen es obligatorio")
        actual = await self.repo.ingrediente(ingrediente_id, bloquear=True)
        if actual is None:
            raise NoEncontrado("El ingrediente no existe")
        if not actual["activo"]:
            raise ReglaDeNegocio("No se puede reponer un ingrediente inactivo")
        return await self.repo.reponer(
            ingrediente_id, cantidad, usuario_id=usuario_id, origen=origen.strip()
        )

    async def historial(
        self,
        *,
        ingrediente_id: int | None = None,
        desde: date | None = None,
        hasta: date | None = None,
        tipo: str | None = None,
    ) -> list[dict]:
        if desde is not None and hasta is not None and desde > hasta:
            raise DatosInvalidos("El rango de fechas no es valido")
        if tipo is not None and tipo not in TIPOS_MOVIMIENTO:
            raise DatosInvalidos("El tipo de movimiento no es valido")
        if ingrediente_id is not None and await self.repo.ingrediente(ingrediente_id) is None:
            raise NoEncontrado("El ingrediente no existe")
        return await self.repo.historial(
            ingrediente_id=ingrediente_id, desde=desde, hasta=hasta, tipo=tipo
        )

    @staticmethod
    def _validar(datos: DatosIngrediente) -> DatosIngrediente:
        try:
            return validar_ingrediente(datos)
        except ValueError as exc:
            raise DatosInvalidos(str(exc)) from exc

    async def _comprobar_referencias(self, datos: DatosIngrediente) -> None:
        if datos.responsable_id is not None and not await self.repo.responsable_valido(
            datos.responsable_id
        ):
            raise DatosInvalidos("El responsable no existe o no esta activo")
