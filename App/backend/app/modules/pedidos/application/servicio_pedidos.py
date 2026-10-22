"""Creacion, consulta y avance de pedidos."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.errores import DatosInvalidos, NoEncontrado, ReglaDeNegocio
from app.modules.pedidos.application.edicion_items import RepositorioEdicionItems, preparar_items
from app.modules.pedidos.domain.entidades import EstadoPedido, puede_transicionar


@dataclass(frozen=True, slots=True)
class ItemNuevoPedido:
    producto_id: int
    cantidad: int
    aclaraciones: str | None = None
    variante: str | None = None


class RepositorioPedidos(RepositorioEdicionItems, Protocol):
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
    async def costo_localidad(self, localidad: str) -> Decimal | None: ...
    async def neto_cobrado(self, pedido_id: int) -> Decimal: ...
    async def guardar_edicion(
        self, pedido_id: int, nuevos: dict, *, usuario_id: int | None,
        origen: str, anterior: dict, anteriores: list[dict],
    ) -> dict: ...
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
    async def ajustar_composicion(
        self, pedido_id: int, anteriores: list[dict], nuevos: list[dict],
        version: int, usuario_id: int | None, *, aplicar: bool,
    ) -> None: ...
    async def procesar(self, pedido_id: int, items: list[dict]) -> None: ...
    async def devolver_reserva(self, pedido_id: int, usuario_id: int | None) -> None: ...
    async def reconsumir(
        self, pedido_id: int, items: list[dict], version: int, usuario_id: int | None
    ) -> None: ...


class ServicioPedidos:
    def __init__(self, repo: RepositorioPedidos, stock: ProcesadorStock) -> None:
        self.repo = repo
        self.stock = stock

    async def cotizar_edicion(
        self, pedido_id: int, *, items: list[dict], cambios: dict,
    ) -> dict:
        """Cotiza el resultado completo sin crear direcciones ni modificar la compra."""
        pedido, anteriores, nuevos = await self._preparar_edicion(
            pedido_id, items=items, cambios=cambios,
        )
        await self.stock.ajustar_composicion(
            pedido_id, anteriores, nuevos["items"], pedido["version"], None, aplicar=False,
        )
        return nuevos

    async def editar_edicion(
        self, pedido_id: int, *, items: list[dict], cambios: dict, version_esperada: int,
        total_esperado: Decimal, usuario_id: int | None = None, origen: str = "WHATSAPP",
    ) -> dict:
        """Aplica composicion y operacion con un unico total, version e historial.

        El llamador conserva la unidad de trabajo y debe revertirla ante cualquier
        error: stock, direccion y pedido pertenecen a la misma transaccion.
        """
        if (isinstance(version_esperada, bool) or not isinstance(version_esperada, int)
                or version_esperada < 0):
            raise DatosInvalidos("La version esperada es obligatoria")
        if not isinstance(origen, str) or not origen.strip() or len(origen) > 50:
            raise DatosInvalidos("El origen no es valido")
        if (not isinstance(total_esperado, Decimal) or not total_esperado.is_finite()
                or total_esperado < 0):
            raise DatosInvalidos("El total esperado no es valido")
        pedido, anteriores, nuevos = await self._preparar_edicion(
            pedido_id, items=items, cambios=cambios, version_esperada=version_esperada,
        )
        if nuevos["total"] != total_esperado:
            raise ReglaDeNegocio("El total cambio; revise y confirme nuevamente la propuesta")
        await self.stock.ajustar_composicion(
            pedido_id, anteriores, nuevos["items"], pedido["version"], usuario_id, aplicar=True,
        )
        if nuevos["direccion_nueva"] is not None:
            nuevos["direccion_id"] = await self.repo.crear_direccion(
                pedido["cliente_id"], nuevos["direccion_nueva"],
            )
            if nuevos["direccion_id"] is None:
                raise DatosInvalidos("La direccion no tiene cobertura activa")
        return await self.repo.guardar_edicion(
            pedido_id, nuevos, usuario_id=usuario_id, origen=origen.strip(),
            anterior=pedido, anteriores=anteriores,
        )

    async def _preparar_edicion(
        self, pedido_id: int, *, items: list[dict], cambios: dict,
        version_esperada: int | None = None,
    ) -> tuple[dict, list[dict], dict]:
        permitidos = {"tipo_entrega", "direccion_id", "direccion_nueva",
                      "metodo_pago_acordado", "observaciones"}
        if not isinstance(cambios, dict) or set(cambios) - permitidos:
            raise DatosInvalidos("Los datos del cambio no son validos")
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        self._comprobar_version(pedido, version_esperada)
        if (pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"}
                or pedido.get("preparacion_en") or pedido.get("asignado")):
            raise ReglaDeNegocio("La modificacion requiere revision del personal")
        nuevos = {**pedido, **cambios, "direccion_nueva": cambios.get("direccion_nueva")}
        if (not isinstance(nuevos["tipo_entrega"], str)
                or nuevos["tipo_entrega"] not in {"DELIVERY", "RETIRO"}):
            raise DatosInvalidos("La modalidad no es valida")
        if (not isinstance(nuevos["metodo_pago_acordado"], str)
                or nuevos["metodo_pago_acordado"] not in {"EFECTIVO", "TRANSFERENCIA"}):
            raise DatosInvalidos("El metodo acordado no es valido")
        observaciones = nuevos.get("observaciones")
        if observaciones is not None and (
            not isinstance(observaciones, str) or len(observaciones) > 500
        ):
            raise DatosInvalidos("Las observaciones no son validas")
        if nuevos["tipo_entrega"] == "RETIRO":
            if nuevos["direccion_nueva"] is not None or cambios.get("direccion_id") is not None:
                raise DatosInvalidos("La direccion requiere modalidad delivery")
            nuevos["direccion_id"] = None
            nuevos["costo_envio"] = Decimal("0")
        elif nuevos["direccion_nueva"] is not None:
            if cambios.get("direccion_id") is not None:
                raise DatosInvalidos("Indique una sola direccion")
            direccion = self._validar_direccion_edicion(nuevos["direccion_nueva"])
            nuevos["direccion_nueva"] = direccion
            nuevos["direccion_id"] = None
            nuevos["costo_envio"] = await self.repo.costo_localidad(direccion["localidad"])
        else:
            direccion_id = nuevos.get("direccion_id")
            if (isinstance(direccion_id, bool) or not isinstance(direccion_id, int)
                    or direccion_id <= 0
                    or not await self.repo.direccion_valida(pedido["cliente_id"], direccion_id)):
                raise DatosInvalidos("La direccion no pertenece al cliente o no tiene cobertura")
            nuevos["costo_envio"] = await self.repo.costo_direccion(direccion_id)
        if nuevos["costo_envio"] is None:
            raise DatosInvalidos("La direccion no tiene cobertura activa")
        anteriores = await self.repo.items_edicion(pedido_id)
        nuevos["items"] = await preparar_items(self.repo, anteriores, items)
        nuevos["subtotal"] = sum((item["subtotal"] for item in nuevos["items"]), Decimal("0"))
        nuevos["total"] = nuevos["subtotal"] + nuevos["costo_envio"] - pedido["descuento_total"]
        if nuevos["total"] < 0:
            raise ReglaDeNegocio("El nuevo total no puede ser negativo")
        if nuevos["total"] < await self.repo.neto_cobrado(pedido_id):
            raise ReglaDeNegocio(
                "El nuevo total es menor al neto cobrado; gestione el reintegro primero"
            )
        return pedido, anteriores, nuevos

    @staticmethod
    def _validar_direccion_edicion(datos: dict) -> dict:
        campos = {"calle", "numero", "localidad", "referencia"}
        if not isinstance(datos, dict) or set(datos) - campos:
            raise DatosInvalidos("La direccion no es valida")
        direccion = {**datos, "numero": datos.get("numero", "S/N")}
        for campo, maximo in (("calle", 160), ("numero", 30), ("localidad", 100)):
            valor = direccion.get(campo)
            if not isinstance(valor, str) or not valor.strip() or len(valor) > maximo:
                raise DatosInvalidos("La direccion no es valida")
            direccion[campo] = valor.strip()
        referencia = direccion.get("referencia")
        if referencia is not None and (not isinstance(referencia, str) or len(referencia) > 300):
            raise DatosInvalidos("La referencia no es valida")
        return direccion

    async def cotizar_items(self, pedido_id: int, items: list[dict]) -> dict:
        pedido, anteriores, nuevos, subtotal, total = await self._preparar_edicion_items(
            pedido_id, items
        )
        await self.stock.ajustar_composicion(
            pedido_id, anteriores, nuevos, pedido["version"], None, aplicar=False
        )
        return {"items": nuevos, "subtotal": subtotal, "total": total, "version": pedido["version"]}

    async def editar_items(
        self, pedido_id: int, *, items: list[dict], version_esperada: int,
        usuario_id: int | None = None, origen: str = "WHATSAPP",
        total_esperado: Decimal | None = None,
    ) -> dict:
        if (isinstance(version_esperada, bool) or not isinstance(version_esperada, int)
                or version_esperada < 0):
            raise DatosInvalidos("La version esperada es obligatoria")
        if not isinstance(origen, str) or not origen.strip() or len(origen) > 50:
            raise DatosInvalidos("El origen no es valido")
        if total_esperado is not None and (
            not isinstance(total_esperado, Decimal)
            or not total_esperado.is_finite() or total_esperado < 0
        ):
            raise DatosInvalidos("El total esperado no es valido")
        pedido, anteriores, nuevos, subtotal, total = await self._preparar_edicion_items(
            pedido_id, items, version_esperada=version_esperada
        )
        if total_esperado is not None and total != total_esperado:
            raise ReglaDeNegocio("El total cambio; revise y confirme nuevamente la propuesta")
        await self.stock.ajustar_composicion(
            pedido_id, anteriores, nuevos, pedido["version"], usuario_id, aplicar=True
        )
        return await self.repo.guardar_items(
            pedido_id, nuevos, subtotal, total, usuario_id=usuario_id,
            origen=origen.strip(), anteriores=anteriores,
        )

    async def _preparar_edicion_items(
        self, pedido_id: int, items: list[dict], *, version_esperada: int | None = None,
    ) -> tuple[dict, list[dict], list[dict], Decimal, Decimal]:
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        self._comprobar_version(pedido, version_esperada)
        if (pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"}
                or pedido.get("preparacion_en") or pedido.get("asignado")):
            raise ReglaDeNegocio("La modificacion requiere revision del personal")
        anteriores = await self.repo.items_edicion(pedido_id)
        nuevos = await preparar_items(self.repo, anteriores, items)
        subtotal = sum((item["subtotal"] for item in nuevos), Decimal("0"))
        total = subtotal + pedido["costo_envio"] - pedido["descuento_total"]
        if total < 0:
            raise ReglaDeNegocio("El nuevo total no puede ser negativo")
        if total < await self.repo.neto_cobrado(pedido_id):
            raise ReglaDeNegocio(
                "El nuevo total es menor al neto cobrado; gestione el reintegro primero"
            )
        return pedido, anteriores, nuevos, subtotal, total

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
                if seleccionada.get("disponible") is False:
                    raise ReglaDeNegocio("La variante seleccionada esta sin stock o inactiva")
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
                    **({"variante": variante} if variante is not None else {}),
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
        permitir_correccion: bool | None = None,
        permitir_recuperacion: bool | None = None,
    ) -> dict:
        pedido = await self.repo.obtener(pedido_id, bloquear=True)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        actual = EstadoPedido(pedido["estado"])
        self._comprobar_version(pedido, version_esperada, estado_esperado)
        if correccion:
            if not motivo or not motivo.strip() or version_esperada is None:
                raise DatosInvalidos("La correccion requiere motivo y version esperada")
            if not (
                rol in {"EMPLEADO", "ADMINISTRADOR", "DUENIO"}
                if permitir_correccion is None else permitir_correccion
            ):
                raise ReglaDeNegocio("La correccion requiere personal autorizado")
        cerrado = actual in {EstadoPedido.CANCELADO, EstadoPedido.ENTREGADO}
        recuperacion = correccion and cerrado
        retroceso_inicio = correccion and (actual, nuevo) in {
            (EstadoPedido.EN_PREPARACION, EstadoPedido.PENDIENTE),
            (EstadoPedido.EN_PREPARACION, EstadoPedido.CONFIRMADO),
            (EstadoPedido.CONFIRMADO, EstadoPedido.PENDIENTE),
        }
        if retroceso_inicio and tratamiento_stock != "CONSERVAR":
            raise DatosInvalidos("El retroceso requiere tratamiento_stock CONSERVAR explicito")
        # Corregir la captura no deshace una cocina que ya empezo: el consumo y
        # preparacion_en siguen vigentes incluso si el estado vuelve a pendiente.
        retroceso = (
            retroceso_inicio
            or correccion
            and (
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
        )
        retiro_entregado = (
            actual == EstadoPedido.LISTO
            and nuevo == EstadoPedido.ENTREGADO
            and pedido.get("tipo_entrega") == "RETIRO"
        )
        if recuperacion:
            if not (
                rol in {"ADMINISTRADOR", "DUENIO"}
                if permitir_recuperacion is None else permitir_recuperacion
            ):
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
        if (
            recuperacion and actual == EstadoPedido.ENTREGADO and nuevo == EstadoPedido.LISTO
            and pedido.get("tipo_entrega") == "DELIVERY" and pedido.get("vinculo_logistico")
        ):
            raise ReglaDeNegocio(
                "Debe corregir la entrega desde reparto y confirmar el regreso al local"
            )
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
