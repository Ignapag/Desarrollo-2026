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
            if direccion_id is None or not await self.repo.direccion_valida(cliente_id, direccion_id):
                raise DatosInvalidos("La direccion no pertenece al cliente o esta inactiva")
        if not items:
            raise DatosInvalidos("El pedido debe contener al menos un producto")

        cantidades: dict[int, int] = {}
        aclaraciones: dict[int, str | None] = {}
        for item in items:
            if item.producto_id <= 0 or item.cantidad <= 0:
                raise DatosInvalidos("El producto o su cantidad no son validos")
            cantidades[item.producto_id] = cantidades.get(item.producto_id, 0) + item.cantidad
            aclaraciones[item.producto_id] = item.aclaraciones

        productos = await self.repo.productos(sorted(cantidades))
        por_id = {fila["id"]: fila for fila in productos}
        faltantes = sorted(set(cantidades) - set(por_id))
        if faltantes:
            raise NoEncontrado("Hay productos inexistentes", {"producto_ids": faltantes})
        no_disponibles = sorted(pid for pid, fila in por_id.items() if not fila["disponible"])
        if no_disponibles:
            raise ReglaDeNegocio(
                "Hay productos sin stock o inactivos", {"producto_ids": no_disponibles}
            )

        items_snapshot = [
            {
                "producto_id": producto_id,
                "nombre_producto": por_id[producto_id]["nombre"],
                "cantidad": cantidad,
                "precio_unitario": por_id[producto_id]["precio_base"],
                "aclaraciones": aclaraciones[producto_id],
            }
            for producto_id, cantidad in cantidades.items()
        ]
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
