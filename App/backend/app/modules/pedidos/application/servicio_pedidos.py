"""Creacion, consulta y avance de pedidos."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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
    async def cliente_para_usuario(self, usuario_id: int) -> int | None: ...
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
        canal: str = "WEB",
        metodo_pago_acordado: str = "EFECTIVO",
    ) -> dict: ...
    async def listar(
        self,
        *,
        cliente_id: int | None,
        repartidor_id: int | None = None,
        q: str | None = None,
        estado: str | None = None,
        activos: bool | None = None,
    ) -> list[dict]: ...
    async def obtener(self, pedido_id: int, *, bloquear: bool = False) -> dict | None: ...
    async def detalle(self, pedido_id: int) -> dict | None: ...
    async def costo_direccion(self, direccion_id: int) -> Decimal | None: ...
    async def neto_cobrado(self, pedido_id: int) -> Decimal: ...
    async def editar_operacion(
        self,
        pedido_id: int,
        nuevos: dict,
        *,
        usuario_id: int | None,
        motivo: str,
        origen: str,
        anterior: dict,
    ) -> dict: ...
    async def items_para_stock(self, pedido_id: int) -> list[dict]: ...
    async def cambiar_estado(
        self,
        pedido_id: int,
        estado: EstadoPedido,
        usuario_id: int | None,
        *,
        motivo: str | None = None,
        origen: str = "PANEL",
        tratamiento_stock: str | None = None,
    ) -> dict: ...


class ProcesadorStock(Protocol):
    async def procesar(self, pedido_id: int, items: list[dict]) -> None: ...
    async def devolver_reserva(self, pedido_id: int, usuario_id: int | None) -> None: ...
    async def reconsumir(
        self, pedido_id: int, items: list[dict], version: int, usuario_id: int | None
    ) -> None: ...


class ServicioPedidos:
    def __init__(self, repo: RepositorioPedidos, stock: ProcesadorStock) -> None:
        self.repo = repo
        self.stock = stock

    async def cliente_para_usuario(self, usuario_id: int) -> int:
        cliente_id = await self.repo.cliente_para_usuario(usuario_id)
        if cliente_id is None:
            raise DatosInvalidos("La cuenta no tiene un cliente activo vinculado")
        return cliente_id

    async def crear(
        self,
        *,
        cliente_id: int,
        tipo_entrega: str,
        direccion_id: int | None,
        direccion_nueva: dict | None,
        observaciones: str | None,
        items: list[ItemNuevoPedido],
        canal: str = "WEB",
        metodo_pago_acordado: str = "EFECTIVO",
    ) -> dict:
        if canal not in {"WEB", "WHATSAPP", "MOSTRADOR"}:
            raise DatosInvalidos("El canal del pedido no es valido")
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
        if len(items) > 50:
            raise DatosInvalidos("El pedido no puede contener mas de 50 lineas")

        cantidades: dict[tuple[int, str | None, str | None], int] = {}
        por_producto: dict[tuple[int, str | None], int] = {}
        for item in items:
            if (
                isinstance(item.producto_id, bool)
                or not isinstance(item.producto_id, int)
                or item.producto_id <= 0
                or isinstance(item.cantidad, bool)
                or not isinstance(item.cantidad, int)
                or not 1 <= item.cantidad <= 50
            ):
                raise DatosInvalidos("El producto o su cantidad no son validos")
            producto_variante = (item.producto_id, item.variante)
            por_producto[producto_variante] = por_producto.get(producto_variante, 0) + item.cantidad
            if por_producto[producto_variante] > 50:
                raise DatosInvalidos("La cantidad acumulada del producto no puede superar 50")
            clave = (item.producto_id, item.variante, item.aclaraciones)
            cantidades[clave] = cantidades.get(clave, 0) + item.cantidad

        ids_solicitados = sorted({producto_id for producto_id, _, _ in cantidades})
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
        for (producto_id, variante, aclaracion), cantidad in cantidades.items():
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
                    "aclaraciones": aclaracion,
                }
            )
        if metodo_pago_acordado not in {"EFECTIVO", "TRANSFERENCIA"}:
            raise DatosInvalidos("El metodo acordado no es valido")
        datos_pago = (
            {"metodo_pago_acordado": metodo_pago_acordado}
            if metodo_pago_acordado != "EFECTIVO"
            else {}
        )
        return await self.repo.crear(
            cliente_id=cliente_id,
            tipo_entrega=tipo_entrega,
            direccion_id=direccion_id,
            observaciones=observaciones,
            items=items_snapshot,
            canal=canal,
            **datos_pago,
        )

    async def listar(
        self,
        *,
        cliente_id: int | None = None,
        repartidor_id: int | None = None,
        q: str | None = None,
        estado: str | None = None,
        activos: bool | None = None,
    ) -> list[dict]:
        if q is not None or estado is not None or activos is not None:
            return await self.repo.listar(
                cliente_id=cliente_id,
                repartidor_id=repartidor_id,
                q=q,
                estado=estado,
                activos=activos,
            )
        if repartidor_id is not None:
            return await self.repo.listar(cliente_id=cliente_id, repartidor_id=repartidor_id)
        return await self.repo.listar(cliente_id=cliente_id)

    async def cambiar_estado(
        self,
        pedido_id: int,
        nuevo: EstadoPedido,
        *,
        usuario_id: int | None,
        motivo: str | None = None,
        version_esperada: int | None = None,
        estado_esperado: str | None = None,
        origen: str = "PANEL",
        rol: str | None = None,
        correccion: bool = False,
        tratamiento_stock: str | None = None,
    ) -> dict:
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        actual = EstadoPedido(pedido["estado"])
        self._comprobar_version(pedido, version_esperada, estado_esperado)
        if correccion:
            if not motivo or not motivo.strip() or version_esperada is None:
                raise DatosInvalidos("La correccion requiere motivo y version esperada")
            if rol not in {"EMPLEADO", "ADMINISTRADOR", "DUENIO"}:
                raise ReglaDeNegocio("La correccion requiere personal autorizado")
        cerrado = actual in {EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO}
        recuperacion = correccion and cerrado
        retroceso = correccion and (
            (actual, nuevo)
            in {
                (EstadoPedido.LISTO, EstadoPedido.EN_PREPARACION),
                (EstadoPedido.EN_CAMINO, EstadoPedido.LISTO),
            }
            or (
                actual in {EstadoPedido.EN_PREPARACION, EstadoPedido.LISTO}
                and nuevo == EstadoPedido.CANCELADO
            )
        )
        retiro_entregado = (
            actual == EstadoPedido.LISTO
            and nuevo == EstadoPedido.ENTREGADO
            and pedido.get("tipo_entrega") == "RETIRO"
        )
        if recuperacion:
            if rol not in {"ADMINISTRADOR", "DUENIO"}:
                raise ReglaDeNegocio("Solo administracion puede recuperar pedidos cerrados")
            if not (
                nuevo == EstadoPedido.EN_PREPARACION
                and tratamiento_stock == "RECONSUMIR"
                or actual == EstadoPedido.ENTREGADO
                and nuevo == EstadoPedido.LISTO
                and tratamiento_stock == "CONSERVAR"
            ):
                raise ReglaDeNegocio("Debe explicitar conservar la entrega erronea o reconsumir")
        if not (puede_transicionar(actual, nuevo) or retroceso or recuperacion or retiro_entregado):
            raise ReglaDeNegocio(f"No se puede cambiar un pedido de {actual.value} a {nuevo.value}")
        if nuevo == EstadoPedido.EN_PREPARACION and pedido.get("puede_preparar") is False:
            raise ReglaDeNegocio("La transferencia debe estar aprobada antes de preparar el pedido")
        if nuevo == EstadoPedido.EN_CAMINO and not (
            pedido.get("tipo_entrega") == "DELIVERY" and pedido.get("salida_real")
        ):
            raise ReglaDeNegocio("La salida requiere delivery asignado y viaje iniciado")
        if (
            nuevo == EstadoPedido.ENTREGADO
            and pedido.get("tipo_entrega") == "DELIVERY"
            and not pedido.get("entrega_real")
        ):
            raise ReglaDeNegocio("La entrega debe registrarse desde el viaje real")
        if (retroceso or recuperacion or nuevo == EstadoPedido.CANCELADO) and pedido.get(
            "asignado"
        ):
            raise ReglaDeNegocio("Debe resolver la asignacion con el personal de reparto")
        if nuevo == EstadoPedido.CANCELADO:
            if actual in {EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO} and not pedido.get(
                "preparacion_en"
            ):
                await self.stock.devolver_reserva(pedido_id, usuario_id)
                tratamiento_stock = "RESERVA_DEVUELTA"
            elif tratamiento_stock != "MERMA":
                raise ReglaDeNegocio("La cancelacion tras cocina requiere declarar MERMA")
        if recuperacion and tratamiento_stock == "RECONSUMIR":
            await self.stock.reconsumir(
                pedido_id,
                await self.repo.items_para_stock(pedido_id),
                pedido["version"] + 1,
                usuario_id,
            )
        elif nuevo == EstadoPedido.EN_PREPARACION or (
            actual == EstadoPedido.PENDIENTE and nuevo == EstadoPedido.CONFIRMADO
        ):
            await self.stock.procesar(pedido_id, await self.repo.items_para_stock(pedido_id))
        if motivo is None and origen == "PANEL" and tratamiento_stock is None:
            return await self.repo.cambiar_estado(pedido_id, nuevo, usuario_id)
        return await self.repo.cambiar_estado(
            pedido_id,
            nuevo,
            usuario_id,
            motivo=motivo,
            origen=origen,
            tratamiento_stock=tratamiento_stock,
        )

    @staticmethod
    def _comprobar_version(pedido: dict, version: int | None, estado: str | None = None) -> None:
        if version is not None and pedido.get("version") != version:
            raise ReglaDeNegocio("El pedido cambio; actualice antes de continuar")
        if estado is not None and pedido["estado"] != estado:
            raise ReglaDeNegocio("El estado del pedido cambio; actualice antes de continuar")

    async def detalle(
        self, pedido_id: int, *, cliente_id: int | None = None, repartidor_id: int | None = None
    ) -> dict:
        pedido = await self.repo.detalle(pedido_id)
        if pedido is None or cliente_id is not None and pedido["cliente_id"] != cliente_id:
            raise NoEncontrado("El pedido no existe")
        if repartidor_id is not None and (
            not pedido.get("envio") or pedido["envio"]["repartidor_id"] != repartidor_id
        ):
            raise NoEncontrado("El pedido no existe")
        return pedido

    async def editar_operacion(
        self,
        pedido_id: int,
        *,
        cambios: dict,
        usuario_id: int | None,
        motivo: str,
        version_esperada: int,
        origen: str = "PANEL",
        rol: str | None = None,
    ) -> dict:
        if not motivo or not motivo.strip() or version_esperada is None:
            raise DatosInvalidos("La edicion requiere motivo y version esperada")
        permitidos = {
            "tipo_entrega",
            "direccion_id",
            "direccion_nueva",
            "metodo_pago_acordado",
            "observaciones",
        }
        if not cambios or set(cambios) - permitidos:
            raise DatosInvalidos("Los datos del cambio no son validos")
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        self._comprobar_version(pedido, version_esperada)
        if pedido["estado"] not in {"PENDIENTE", "CONFIRMADO", "EN_PREPARACION", "LISTO"}:
            raise ReglaDeNegocio("El estado actual requiere una correccion del personal")
        if pedido.get("asignado"):
            raise ReglaDeNegocio("Debe coordinar la desasignacion con el personal de reparto")
        nuevos = {**pedido, **cambios}
        if nuevos["tipo_entrega"] not in {"DELIVERY", "RETIRO"}:
            raise DatosInvalidos("La modalidad no es valida")
        if nuevos["metodo_pago_acordado"] not in {"EFECTIVO", "TRANSFERENCIA"}:
            raise DatosInvalidos("El metodo acordado no es valido")
        if cambios.get("direccion_nueva") is not None:
            nuevos["direccion_id"] = await self.repo.crear_direccion(
                pedido["cliente_id"], cambios["direccion_nueva"]
            )
        if nuevos["tipo_entrega"] == "DELIVERY":
            if not nuevos.get("direccion_id") or not await self.repo.direccion_valida(
                pedido["cliente_id"], nuevos["direccion_id"]
            ):
                raise DatosInvalidos("La direccion no pertenece al cliente o no tiene cobertura")
            nuevos["costo_envio"] = await self.repo.costo_direccion(nuevos["direccion_id"])
            if nuevos["costo_envio"] is None:
                raise DatosInvalidos("La direccion no tiene cobertura activa")
        else:
            nuevos["direccion_id"] = None
            nuevos["costo_envio"] = 0
        nuevos["total"] = pedido["subtotal"] + nuevos["costo_envio"] - pedido["descuento_total"]
        neto = await self.repo.neto_cobrado(pedido_id)
        if nuevos["total"] < neto:
            raise ReglaDeNegocio(
                "El nuevo total es menor al neto cobrado; gestione el reintegro primero"
            )
        return await self.repo.editar_operacion(
            pedido_id,
            nuevos,
            usuario_id=usuario_id,
            motivo=motivo.strip(),
            origen=origen,
            anterior=pedido,
        )
