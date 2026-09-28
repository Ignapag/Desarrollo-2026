"""Creacion, consulta y avance de pedidos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.pedidos.domain.entidades import EstadoPedido, puede_transicionar


@dataclass(frozen=True, slots=True)
class ItemNuevoPedido:
    producto_id: int
    cantidad: int
    aclaraciones: str | None = None
    variante: str | None = None


class RepositorioPedidos(Protocol):
    async def cliente_valido(self, cliente_id: int) -> bool: ...
    async def direccion_valida(self, cliente_id: int, direccion_id: int) -> bool: ...
    async def crear_direccion(self, cliente_id: int, datos: dict) -> int | None: ...
    async def productos(self, ids: list[int]) -> list[dict]: ...
    async def crear(
        self,
        *,
        cliente_id: int,
        tipo_entrega: str,
        direccion_id: int | None,
        observaciones: str | None,
        items: list[dict],
    ) -> dict: ...
    async def listar(self, *, cliente_id: int | None) -> list[dict]: ...
    async def obtener(self, pedido_id: int, *, bloquear: bool = False) -> dict | None: ...
    async def items_para_stock(self, pedido_id: int) -> list[dict]: ...
    async def cambiar_estado(
        self, pedido_id: int, estado: EstadoPedido, usuario_id: int | None
    ) -> dict: ...


class ProcesadorStock(Protocol):
    async def procesar(self, pedido_id: int, items: list[dict]) -> None: ...


class ServicioPedidos:
    def __init__(self, repo: RepositorioPedidos, stock: ProcesadorStock) -> None:
        self.repo = repo
        self.stock = stock

    async def crear(
        self,
        *,
        cliente_id: int,
        tipo_entrega: str,
        direccion_id: int | None,
        direccion_nueva: dict | None,
        observaciones: str | None,
        items: list[ItemNuevoPedido],
    ) -> dict:
        if cliente_id <= 0 or not await self.repo.cliente_valido(cliente_id):
            raise DatosInvalidos("El cliente no existe o esta inactivo")
        if tipo_entrega not in {"DELIVERY", "RETIRO"}:
            raise DatosInvalidos("El tipo de entrega no es valido")
        if tipo_entrega == "DELIVERY":
            if direccion_id is None and direccion_nueva is not None:
                direccion_id = await self.repo.crear_direccion(cliente_id, direccion_nueva)
                if direccion_id is None:
                    raise DatosInvalidos("La zona indicada no existe o esta inactiva")
            if direccion_id is None or not await self.repo.direccion_valida(
                cliente_id, direccion_id
            ):
                raise DatosInvalidos("La direccion no pertenece al cliente o esta inactiva")
        if not items:
            raise DatosInvalidos("El pedido debe contener al menos un producto")

        cantidades: dict[tuple[int, str | None], int] = {}
        aclaraciones: dict[tuple[int, str | None], str | None] = {}
        for item in items:
            if item.producto_id <= 0 or item.cantidad <= 0:
                raise DatosInvalidos("El producto o su cantidad no son validos")
            clave = (item.producto_id, item.variante)
            cantidades[clave] = cantidades.get(clave, 0) + item.cantidad
            aclaraciones[clave] = item.aclaraciones

        ids_solicitados = sorted({producto_id for producto_id, _ in cantidades})
        productos = await self.repo.productos(ids_solicitados)
        por_id = {fila["id"]: fila for fila in productos}
        faltantes = sorted(set(ids_solicitados) - set(por_id))
        if faltantes:
            raise NoEncontrado("Hay productos inexistentes", {"producto_ids": faltantes})
        no_disponibles = sorted(pid for pid, fila in por_id.items() if not fila["disponible"])
        if no_disponibles:
            raise ReglaDeNegocio(
                "Hay productos sin stock o inactivos", {"producto_ids": no_disponibles}
            )

        items_snapshot: list[dict] = []
        for (producto_id, variante), cantidad in cantidades.items():
            producto = por_id[producto_id]
            variantes = producto.get("variantes") or []
            precio = producto["precio_base"]
            nombre = producto["nombre"]
            if variantes:
                seleccionada = next(
                    (item for item in variantes if item["nombre"] == variante), None
                )
                if seleccionada is None:
                    raise DatosInvalidos(
                        f"Debe seleccionar una variante valida para {producto['nombre']}"
                    )
                precio = seleccionada["precio"]
                nombre = f"{nombre} ({seleccionada['nombre']})"
            elif variante is not None:
                raise DatosInvalidos(f"El producto {producto['nombre']} no tiene variantes")
            items_snapshot.append(
                {
                    "producto_id": producto_id,
                    "nombre_producto": nombre,
                    "cantidad": cantidad,
                    "precio_unitario": precio,
                    "aclaraciones": aclaraciones[(producto_id, variante)],
                }
            )
        return await self.repo.crear(
            cliente_id=cliente_id,
            tipo_entrega=tipo_entrega,
            direccion_id=direccion_id,
            observaciones=observaciones,
            items=items_snapshot,
        )

    async def listar(self, *, cliente_id: int | None = None) -> list[dict]:
        return await self.repo.listar(cliente_id=cliente_id)

    async def cambiar_estado(
        self, pedido_id: int, nuevo: EstadoPedido, *, usuario_id: int | None
    ) -> dict:
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        actual = EstadoPedido(pedido["estado"])
        if not puede_transicionar(actual, nuevo):
            raise ReglaDeNegocio(
                f"No se puede cambiar un pedido de {actual.value} a {nuevo.value}"
            )
        if actual == EstadoPedido.PENDIENTE and nuevo in {
            EstadoPedido.CONFIRMADO,
            EstadoPedido.EN_PREPARACION,
        }:
            await self.stock.procesar(pedido_id, await self.repo.items_para_stock(pedido_id))
        return await self.repo.cambiar_estado(pedido_id, nuevo, usuario_id)
