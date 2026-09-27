"""Casos de uso de ingredientes, reposicion, historial y alertas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.core.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.domain.entidades import (
    NIVELES,
    TIPOS_MOVIMIENTO,
    DatosIngrediente,
    ItemConsumoStock,
    validar_ingrediente,
    validar_reposicion,
)


class RepositorioStock(Protocol):
    async def bloquear_pedido(self, pedido_id: int) -> bool: ...
    async def consumo_existente(self, pedido_id: int) -> bool: ...
    async def pedido_tiene_opciones(self, pedido_id: int) -> bool: ...
    async def recetas(self, producto_ids: list[int]) -> list[dict]: ...
    async def bloquear_ingredientes(self, ingrediente_ids: list[int]) -> list[dict]: ...
    async def consumir(
        self, ingrediente_id: int, cantidad: Decimal, pedido_id: int
    ) -> dict | None: ...
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


class PedidoYaProcesado(ReglaDeNegocio):
    codigo = "pedido_ya_procesado"


class StockInsuficiente(ReglaDeNegocio):
    codigo = "stock_insuficiente"


class ServicioStock:
    def __init__(self, repositorio: RepositorioStock) -> None:
        self.repo = repositorio

    async def procesar_consumo(
        self, pedido_id: int, items: Sequence[ItemConsumoStock]
    ) -> list[dict]:
        """Consume una vez por pedido dentro de la transaccion del llamador.

        Pedidos debera usar la misma UnidadDeTrabajo y propagar los errores para
        que se reviertan tanto la confirmacion como el consumo.
        """
        if isinstance(pedido_id, bool) or not isinstance(pedido_id, int) or pedido_id <= 0:
            raise DatosInvalidos("El pedido_id no es valido")
        if not items:
            raise DatosInvalidos("El pedido debe contener al menos un item")
        cantidades: dict[int, int] = {}
        for item in items:
            if not isinstance(item, ItemConsumoStock):
                raise DatosInvalidos("El item de consumo no es valido")
            if (
                isinstance(item.producto_id, bool)
                or not isinstance(item.producto_id, int)
                or item.producto_id <= 0
                or isinstance(item.cantidad, bool)
                or not isinstance(item.cantidad, int)
                or item.cantidad <= 0
            ):
                raise DatosInvalidos("El producto o su cantidad no es valido")
            if item.opciones:
                raise ReglaDeNegocio("El consumo con personalizaciones todavia no esta soportado")
            cantidades[item.producto_id] = cantidades.get(item.producto_id, 0) + item.cantidad

        # El bloqueo de la fila del pedido serializa intentos simultaneos del
        # mismo pedido sin cambiar su estado ni requerir una migracion.
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        if await self.repo.consumo_existente(pedido_id):
            raise PedidoYaProcesado("El pedido ya consumio stock", {"pedido_id": pedido_id})
        if await self.repo.pedido_tiene_opciones(pedido_id):
            raise ReglaDeNegocio("El consumo con personalizaciones todavia no esta soportado")

        recetas = await self.repo.recetas(sorted(cantidades))
        encontrados = {fila["producto_id"] for fila in recetas}
        faltan_productos = sorted(cantidades.keys() - encontrados)
        if faltan_productos:
            raise NoEncontrado("Hay productos inexistentes", {"producto_ids": faltan_productos})
        sin_receta = {fila["producto_id"] for fila in recetas if fila["ingrediente_id"] is None}
        if sin_receta:
            raise ReglaDeNegocio("Hay productos sin receta", {"producto_ids": sorted(sin_receta)})

        requeridos: dict[int, Decimal] = {}
        for fila in recetas:
            ingrediente_id = fila["ingrediente_id"]
            requeridos[ingrediente_id] = requeridos.get(ingrediente_id, Decimal("0")) + (
                fila["cantidad_requerida"] * cantidades[fila["producto_id"]]
            )

        bloqueados = await self.repo.bloquear_ingredientes(sorted(requeridos))
        saldos = {fila["id"]: fila for fila in bloqueados}
        if set(requeridos) != set(saldos):
            raise ReglaDeNegocio("La receta contiene ingredientes inexistentes")
        faltantes = [
            {
                "ingrediente_id": ingrediente_id,
                "nombre": saldos[ingrediente_id]["nombre"],
                "cantidad_requerida": requerido,
                "cantidad_disponible": saldos[ingrediente_id]["cantidad_actual"],
            }
            for ingrediente_id, requerido in sorted(requeridos.items())
            if saldos[ingrediente_id]["cantidad_actual"] < requerido
        ]
        if faltantes:
            raise StockInsuficiente(
                "Stock insuficiente para el pedido", {"ingredientes": faltantes}
            )

        movimientos = []
        for ingrediente_id, requerido in sorted(requeridos.items()):
            movimiento = await self.repo.consumir(ingrediente_id, requerido, pedido_id)
            if movimiento is None:
                raise StockInsuficiente(
                    "El stock cambio durante el descuento",
                    {"ingrediente_id": ingrediente_id},
                )
            movimientos.append(movimiento)
        return movimientos

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
