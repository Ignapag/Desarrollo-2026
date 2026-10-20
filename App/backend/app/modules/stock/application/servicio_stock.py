"""Casos de uso de ingredientes, reposicion, historial y alertas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.stock.domain.entidades import (
    INGREDIENTES_QUITABLES,
    NIVELES,
    TIPOS_MOVIMIENTO,
    DatosIngrediente,
    ItemConsumoStock,
    cantidades_de_snapshot,
    ingredientes_omitidos_de_aclaraciones,
    validar_ingrediente,
    validar_reposicion,
)


class RepositorioStock(Protocol):
    async def reservas_antes_preparacion(self, pedido_id: int) -> list[dict] | None: ...
    async def bloquear_pedido(self, pedido_id: int) -> bool: ...
    async def consumo_existente(self, pedido_id: int) -> bool: ...
    async def pedido_tiene_opciones(self, pedido_id: int) -> bool: ...
    async def recetas(self, producto_ids: list[int]) -> list[dict]: ...
    async def bloquear_ingredientes(self, ingrediente_ids: list[int]) -> list[dict]: ...
    async def consumir(
        self,
        ingrediente_id: int,
        cantidad: Decimal,
        pedido_id: int,
        *,
        motivo: str | None = None,
        usuario_id: int | None = None,
    ) -> dict | None: ...
    async def item_para_ajuste(self, pedido_id: int, item_id: int) -> dict | None: ...
    async def ajuste_existente(self, pedido_id: int, motivo: str) -> bool: ...
    async def ingrediente_item_para_devolucion(
        self, pedido_id: int, item_id: int, nombre: str
    ) -> dict | None: ...
    async def devolucion_existente(self, pedido_id: int, motivo: str) -> bool: ...
    async def consumo_neto_ingrediente(self, pedido_id: int, ingrediente_id: int) -> Decimal: ...
    async def devolver(
        self,
        ingrediente_id: int,
        cantidad: Decimal,
        pedido_id: int,
        usuario_id: int | None,
        motivo: str,
    ) -> None: ...
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

    async def ajustar_composicion(
        self, pedido_id: int, anteriores: Sequence[ItemConsumoStock],
        nuevos: Sequence[ItemConsumoStock], version: int, usuario_id: int | None,
        *, aplicar: bool = True,
    ) -> None:
        """Valida toda la demanda y aplica solo su diferencial en el UoW del pedido."""
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        if await self.repo.reservas_antes_preparacion(pedido_id) is None:
            raise ReglaDeNegocio("Solo se puede editar la composicion antes de cocina")
        if await self.repo.pedido_tiene_opciones(pedido_id):
            raise ReglaDeNegocio(
                "La edicion con opciones estructuradas requiere revision del personal"
            )
        motivo = f"EDICION_ITEMS:v{version}"
        if aplicar and await self.repo.ajuste_existente(pedido_id, motivo):
            raise ReglaDeNegocio("La version ya tiene un ajuste de composicion")
        consumido = await self.repo.consumo_existente(pedido_id)
        grupos = (anteriores, nuevos)
        sin_snapshot = {
            item.producto_id for grupo in grupos for item in grupo
            if item.receta_snapshot is None
        }
        recetas = await self.repo.recetas(sorted(sin_snapshot)) if sin_snapshot else []
        normalizados = []
        ingrediente_ids = set()
        for grupo in grupos:
            filas = []
            for item in grupo:
                receta = item.receta_snapshot
                if receta is None:
                    receta = tuple(
                        (fila["ingrediente_id"], fila["cantidad_requerida"])
                        for fila in recetas if fila["producto_id"] == item.producto_id
                    )
                if not receta or any(
                    isinstance(i, bool) or not isinstance(i, int) or i <= 0
                    or not isinstance(c, Decimal) or not c.is_finite() or c <= 0
                    for i, c in receta
                ):
                    raise ReglaDeNegocio("La receta del pedido no es valida")
                ingrediente_ids.update(i for i, _ in receta)
                filas.append((item, receta))
            normalizados.append(filas)
        saldos = {
            fila["id"]: fila
            for fila in await self.repo.bloquear_ingredientes(sorted(ingrediente_ids))
        }
        if set(saldos) != ingrediente_ids:
            raise ReglaDeNegocio("La receta contiene ingredientes inexistentes")
        demandas = []
        for grupo in normalizados:
            demanda = {}
            for item, receta in grupo:
                for ingrediente_id, cantidad in receta:
                    if saldos[ingrediente_id]["nombre"].casefold() in item.ingredientes_omitidos:
                        continue
                    demanda[ingrediente_id] = (
                        demanda.get(ingrediente_id, Decimal("0")) + cantidad * item.cantidad
                    )
            demandas.append(demanda)
        antes, despues = demandas
        for ingrediente_id in sorted(ingrediente_ids):
            demanda_adicional = (
                despues.get(ingrediente_id, Decimal("0"))
                - antes.get(ingrediente_id, Decimal("0"))
            )
            if demanda_adicional > 0 and not saldos[ingrediente_id]["activo"]:
                raise ReglaDeNegocio(
                    "La modificacion requiere un ingrediente inactivo",
                    {"ingrediente_id": ingrediente_id},
                )
        deltas = {
            i: despues.get(i, Decimal("0")) - (antes.get(i, Decimal("0")) if consumido else 0)
            for i in ingrediente_ids
        }
        for ingrediente_id, delta in sorted(deltas.items()):
            if delta > saldos[ingrediente_id]["cantidad_actual"]:
                raise StockInsuficiente(
                    "Stock insuficiente para modificar el pedido",
                    {"ingrediente_id": ingrediente_id},
                )
            neto = (
                await self.repo.consumo_neto_ingrediente(pedido_id, ingrediente_id)
                if delta < 0 else Decimal("0")
            )
            if delta < 0 and neto < -delta:
                raise ReglaDeNegocio("La devolucion supera el consumo neto registrado")
        if not aplicar or not consumido:
            return
        for ingrediente_id, delta in sorted(deltas.items()):
            if delta > 0:
                if await self.repo.consumir(
                    ingrediente_id, delta, pedido_id, motivo=motivo, usuario_id=usuario_id
                ) is None:
                    raise StockInsuficiente("El stock cambio durante el ajuste")
            elif delta < 0:
                await self.repo.devolver(ingrediente_id, -delta, pedido_id, usuario_id, motivo)

    async def procesar_consumo(
        self,
        pedido_id: int,
        items: Sequence[ItemConsumoStock],
        *,
        clave_ciclo: str | None = None,
        usuario_id: int | None = None,
    ) -> list[dict]:
        """Consume una vez por pedido dentro de la transaccion del llamador.

        Pedidos debera usar la misma UnidadDeTrabajo y propagar los errores para
        que se reviertan tanto la confirmacion como el consumo.
        """
        if isinstance(pedido_id, bool) or not isinstance(pedido_id, int) or pedido_id <= 0:
            raise DatosInvalidos("El pedido_id no es valido")
        if not items:
            raise DatosInvalidos("El pedido debe contener al menos un item")
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
            if not isinstance(item.ingredientes_omitidos, tuple) or any(
                not isinstance(nombre, str) or nombre not in INGREDIENTES_QUITABLES
                for nombre in item.ingredientes_omitidos
            ):
                raise ReglaDeNegocio("Hay ingredientes que no se pueden retirar")

        # El bloqueo de la fila del pedido serializa intentos simultaneos del
        # mismo pedido sin cambiar su estado ni requerir una migracion.
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        if clave_ciclo is not None and await self.repo.ajuste_existente(pedido_id, clave_ciclo):
            raise PedidoYaProcesado("El ciclo ya consumio stock")
        if clave_ciclo is None and await self.repo.consumo_existente(pedido_id):
            raise PedidoYaProcesado("El pedido ya consumio stock", {"pedido_id": pedido_id})
        if await self.repo.pedido_tiene_opciones(pedido_id):
            raise ReglaDeNegocio("El consumo con personalizaciones todavia no esta soportado")

        productos_sin_snapshot = {
            item.producto_id for item in items if item.receta_snapshot is None
        }
        recetas = (
            await self.repo.recetas(sorted(productos_sin_snapshot))
            if productos_sin_snapshot else []
        )
        encontrados = {fila["producto_id"] for fila in recetas}
        faltan_productos = sorted(productos_sin_snapshot - encontrados)
        if faltan_productos:
            raise NoEncontrado("Hay productos inexistentes", {"producto_ids": faltan_productos})
        sin_receta = {fila["producto_id"] for fila in recetas if fila["ingrediente_id"] is None}
        if sin_receta:
            raise ReglaDeNegocio("Hay productos sin receta", {"producto_ids": sorted(sin_receta)})

        recetas_items = []
        for item in items:
            receta = item.receta_snapshot
            if receta is None:
                receta = tuple(
                    (fila["ingrediente_id"], fila["cantidad_requerida"])
                    for fila in recetas if fila["producto_id"] == item.producto_id
                )
            if not receta:
                raise ReglaDeNegocio("Hay productos sin receta")
            if any(
                isinstance(ingrediente_id, bool)
                or not isinstance(ingrediente_id, int) or ingrediente_id <= 0
                or not isinstance(cantidad, Decimal) or not cantidad.is_finite() or cantidad <= 0
                for ingrediente_id, cantidad in receta
            ):
                raise ReglaDeNegocio("La receta del pedido no es valida")
            recetas_items.append((item, receta))
        ingrediente_ids = {
            ingrediente_id for _, receta in recetas_items for ingrediente_id, _ in receta
        }
        bloqueados = await self.repo.bloquear_ingredientes(sorted(ingrediente_ids))
        saldos = {fila["id"]: fila for fila in bloqueados}
        if ingrediente_ids != set(saldos):
            raise ReglaDeNegocio("La receta contiene ingredientes inexistentes")

        requeridos: dict[int, Decimal] = {}
        for item, receta in recetas_items:
            for ingrediente_id, cantidad in receta:
                if saldos[ingrediente_id]["nombre"].casefold() in item.ingredientes_omitidos:
                    continue
                requeridos[ingrediente_id] = requeridos.get(ingrediente_id, Decimal("0")) + (
                    cantidad * item.cantidad
                )
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
            if clave_ciclo is None:
                movimiento = await self.repo.consumir(ingrediente_id, requerido, pedido_id)
            else:
                movimiento = await self.repo.consumir(
                    ingrediente_id,
                    requerido,
                    pedido_id,
                    motivo=clave_ciclo,
                    usuario_id=usuario_id,
                )
            if movimiento is None:
                raise StockInsuficiente(
                    "El stock cambio durante el descuento",
                    {"ingrediente_id": ingrediente_id},
                )
            movimientos.append(movimiento)
        return movimientos

    async def devolver_reserva_pedido(self, pedido_id: int, usuario_id: int | None) -> None:
        """Devuelve el neto reservado solo cuando nunca comenzo la cocina."""
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        reservas = await self.repo.reservas_antes_preparacion(pedido_id)
        if reservas is None:
            raise ReglaDeNegocio("Los insumos utilizados no se devuelven automaticamente")
        await self.repo.bloquear_ingredientes([fila["ingrediente_id"] for fila in reservas])
        for fila in reservas:
            if fila["cantidad"] > 0:
                await self.repo.devolver(
                    fila["ingrediente_id"],
                    fila["cantidad"],
                    pedido_id,
                    usuario_id,
                    "CANCELACION_RESERVA",
                )

    async def ajustar_cantidad_item(
        self,
        pedido_id: int,
        item_id: int,
        nueva_cantidad: int,
        clave_cambio: str,
        usuario_id: int | None,
    ) -> None:
        """Ajusta solo el diferencial antes de actualizar el item, en el mismo UoW.

        La clave identifica la version confirmada y debe ser unica por cambio.
        Una reduccion desde cocina conserva el consumo como insumos ya utilizados.
        """
        if any(
            isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0
            for valor in (pedido_id, item_id)
        ):
            raise DatosInvalidos("El pedido, item o usuario no es valido")
        if usuario_id is not None and (
            isinstance(usuario_id, bool) or not isinstance(usuario_id, int) or usuario_id <= 0
        ):
            raise DatosInvalidos("El usuario no es valido")
        if (
            isinstance(nueva_cantidad, bool)
            or not isinstance(nueva_cantidad, int)
            or not 1 <= nueva_cantidad <= 50
        ):
            raise DatosInvalidos("La cantidad debe ser un entero entre 1 y 50")
        if not isinstance(clave_cambio, str) or not clave_cambio.strip():
            raise DatosInvalidos("La clave del cambio es obligatoria")
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        item = await self.repo.item_para_ajuste(pedido_id, item_id)
        if item is None:
            raise NoEncontrado("El item no pertenece al pedido")
        if item["estado"] in {"ENTREGADO", "CANCELADO"}:
            raise ReglaDeNegocio("No se puede ajustar stock de un pedido cerrado")
        cocina_iniciada = bool(item.get("preparacion_en")) or item["estado"] not in {
            "PENDIENTE",
            "CONFIRMADO",
        }
        if usuario_id is None and cocina_iniciada:
            raise ReglaDeNegocio("Los cambios en cocina requieren aprobacion del personal")
        motivo = f"WHATSAPP_CANTIDAD:{clave_cambio.strip()}"
        if await self.repo.ajuste_existente(pedido_id, motivo):
            return
        delta = nueva_cantidad - item["cantidad"]
        if delta == 0 or not await self.repo.consumo_existente(pedido_id):
            return
        if delta < 0 and cocina_iniciada:
            return
        if await self.repo.pedido_tiene_opciones(pedido_id):
            raise ReglaDeNegocio("El ajuste con opciones estructuradas todavia no esta soportado")
        snapshot = cantidades_de_snapshot(item.get("receta_snapshot"))
        recetas = (
            [
                {"ingrediente_id": ingrediente_id, "cantidad_requerida": cantidad}
                for ingrediente_id, cantidad in snapshot
            ] if snapshot is not None else await self.repo.recetas([item["producto_id"]])
        )
        if not recetas or any(fila["ingrediente_id"] is None for fila in recetas):
            raise ReglaDeNegocio("El producto no tiene una receta para ajustar el consumo")
        ingrediente_ids = sorted({fila["ingrediente_id"] for fila in recetas})
        ingredientes = await self.repo.bloquear_ingredientes(ingrediente_ids)
        saldos = {fila["id"]: fila for fila in ingredientes}
        if set(saldos) != set(ingrediente_ids):
            raise ReglaDeNegocio("La receta contiene ingredientes inexistentes")
        omitidos = ingredientes_omitidos_de_aclaraciones(item["aclaraciones"])
        requeridos = {
            fila["ingrediente_id"]: fila["cantidad_requerida"] * abs(delta)
            for fila in recetas
            if saldos[fila["ingrediente_id"]]["nombre"].casefold() not in omitidos
        }
        for ingrediente_id, requerido in sorted(requeridos.items()):
            if delta > 0 and saldos[ingrediente_id]["cantidad_actual"] < requerido:
                raise StockInsuficiente(
                    "Stock insuficiente para aumentar la cantidad",
                    {"ingrediente_id": ingrediente_id},
                )
            if delta < 0:
                neto = await self.repo.consumo_neto_ingrediente(pedido_id, ingrediente_id)
                if neto < requerido:
                    raise ReglaDeNegocio("La devolucion supera el consumo neto del ingrediente")
        for ingrediente_id, requerido in sorted(requeridos.items()):
            if delta > 0:
                resultado = await self.repo.consumir(
                    ingrediente_id, requerido, pedido_id, motivo=motivo, usuario_id=usuario_id
                )
                if resultado is None:
                    raise StockInsuficiente("El stock cambio durante el ajuste")
            else:
                await self.repo.devolver(ingrediente_id, requerido, pedido_id, usuario_id, motivo)

    async def devolver_ingrediente_antes_preparacion(
        self, pedido_id: int, item_id: int, nombre: str, usuario_id: int | None = None
    ) -> None:
        """Devuelve un retiro de ingrediente antes de guardar la nueva aclaracion.

        Usa el item y la receta persistidos y la misma transaccion del cambio.
        El bloqueo del pedido serializa preparacion, devoluciones y reintentos.
        """
        if any(
            isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0
            for valor in (pedido_id, item_id)
        ):
            raise DatosInvalidos("El pedido o item no es valido")
        nombre = nombre.strip().casefold() if isinstance(nombre, str) else ""
        if nombre not in INGREDIENTES_QUITABLES:
            raise DatosInvalidos("El ingrediente no se puede retirar")
        if not await self.repo.bloquear_pedido(pedido_id):
            raise NoEncontrado("El pedido no existe")
        item = await self.repo.ingrediente_item_para_devolucion(pedido_id, item_id, nombre)
        if item is None:
            raise NoEncontrado("El item o ingrediente no pertenece al pedido")
        if item["estado"] not in {"PENDIENTE", "CONFIRMADO"} or item.get("preparacion_en"):
            raise ReglaDeNegocio("Solo se devuelve stock antes de comenzar la preparacion")
        ingrediente_id = item["ingrediente_id"]
        motivo = f"WHATSAPP_RETIRO:{item_id}:{ingrediente_id}"
        if await self.repo.devolucion_existente(pedido_id, motivo):
            return
        notas = {nota.strip().casefold() for nota in (item["aclaraciones"] or "").split(",")}
        if f"sin {nombre}" in notas:
            return
        cantidad = item["cantidad_requerida"] * item["cantidad"]
        neto = await self.repo.consumo_neto_ingrediente(pedido_id, ingrediente_id)
        if cantidad <= 0 or neto < cantidad:
            raise ReglaDeNegocio("La devolucion supera el consumo neto registrado del ingrediente")
        await self.repo.devolver(ingrediente_id, cantidad, pedido_id, usuario_id, motivo)

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
