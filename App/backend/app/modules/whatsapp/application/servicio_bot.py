"""Orquestación del bot: la interpretación propone; estas reglas deciden."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from urllib.parse import quote

from app.errores import DatosInvalidos, ErrorDominio, NoEncontrado, ReglaDeNegocio
from app.modules.pedidos.application.servicio_pedidos import ItemNuevoPedido, ServicioPedidos
from app.modules.stock.application.servicio_stock import INGREDIENTES_QUITABLES, ServicioStock
from app.modules.whatsapp.domain.mensajes import (
    LIMITE_INTERPRETACION,
    SALUDO_BORRADOR,
    es_comando_guiado,
    es_saludo_borrador,
    hash_referencia,
    referencias_en,
    resumen,
    sin_referencias,
    tiene_token_referencia,
)


class RepositorioBot(Protocol):
    async def crear_borrador(self, referencia_hash, cliente_id, datos) -> dict: ...
    async def recibir(
        self, identificador, telefono, texto, media_id, nombre_remitente=None
    ) -> None: ...
    async def entrada(self, identificador, bloquear=False) -> dict | None: ...
    async def conversacion(
        self, telefono, referencia_hash=None, bloquear=False, nombre_remitente=None
    ) -> dict | None: ...
    async def finalizar(self, entrada, b, respuesta) -> None: ...
    async def pedido(self, pedido_id) -> dict: ...
    async def ingredientes(self, producto_id) -> list[dict]: ...
    async def historial(self, b, accion, anterior, posterior, estado, empleado_id=None) -> dict: ...
    async def aplicar_item(self, pedido, item, cantidad, aclaraciones) -> None: ...
    async def comprobante(self, entrada, pedido_id) -> None: ...
    async def revision(self, comprobante_id) -> dict | None: ...
    async def revisar(self, comprobante, aprobar, empleado_id, motivo) -> dict: ...
    async def cambio(self, cambio_id) -> tuple[dict | None, dict | None]: ...
    async def cerrar_cambio(self, cambio_id, estado, empleado_id, motivo) -> None: ...
    async def actualizar_borrador(self, b) -> None: ...
    async def encolar(self, clave, telefono, texto) -> None: ...
    async def derivar(self, referencia_hash, entrada_id, motivo) -> None: ...
    async def atencion_pendiente(self, referencia_hash) -> bool: ...
    async def atencion(self, atencion_id, bloquear=False) -> dict | None: ...
    async def respuesta_atencion(self, clave) -> dict | None: ...
    async def encolar_respuesta(self, clave, atencion, texto, empleado_id) -> dict: ...
    async def resolver_atencion(self, atencion, empleado_id, resolucion) -> None: ...


class InterpretacionDesactualizada(ReglaDeNegocio):
    """El mismo pedido cambió mientras se interpretaba: corresponde reinterpretar."""

    codigo = "whatsapp_interpretacion_desactualizada"


# Se permite retirar ingredientes de la receta, nunca agregar extras por texto libre.
QUITABLES = INGREDIENTES_QUITABLES
MOTIVOS_DERIVACION = {"SOLICITUD", "PROVEEDOR"}
CONFIRMACIONES = {"confirmar", "confirmo", "confirmar pedido", "confirmo pedido"}
EN_ATENCION = (
    "Un empleado está atendiendo esta conversación. Registré tu mensaje y no apliqué "
    "cambios automáticos; te responderá por este chat."
)
SIN_CONVERSACION = (
    "Enviá la referencia MB- del borrador desde el WhatsApp con el que hiciste el pedido. "
    "Si tenés más de un pedido activo, incluí en el mismo mensaje la referencia "
    "del pedido que querés consultar o modificar."
)
CONVERSACION_CAMBIADA = (
    "El pedido de esta conversación cambió mientras procesábamos tu mensaje. "
    "No apliqué ningún cambio. Repetí la solicitud con la referencia MB- del pedido."
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class ServicioBot:
    def __init__(
        self,
        repo: RepositorioBot,
        pedidos: ServicioPedidos,
        numero_negocio: str = "",
        transferencia: str = "",
        stock: ServicioStock | None = None,
    ):
        self.repo = repo
        self.pedidos = pedidos
        self.numero_negocio = numero_negocio
        self.transferencia = transferencia
        self.stock = stock

    async def crear_borrador(self, cliente_id: int | None, datos: dict) -> dict:
        # El contacto declarado no autentica al cliente: solo Meta vincula el remitente.
        # Los borradores internos anteriores conservan su asociación autenticada.
        contacto = datos.get("contacto")
        if contacto is not None:
            if not isinstance(contacto, dict) or set(contacto) != {
                "nombre", "apellido", "telefono"
            }:
                raise DatosInvalidos("Completá nombre, apellido y teléfono de contacto")
            if any(
                not isinstance(contacto[campo], str) or not 1 <= len(contacto[campo].strip()) <= 80
                for campo in ("nombre", "apellido")
            ) or not isinstance(contacto["telefono"], str) or not re.fullmatch(
                r"[0-9]{11,15}", contacto["telefono"]
            ):
                raise DatosInvalidos("Revisá el nombre, apellido y teléfono internacional")
            datos = {**datos, "contacto": {k: v.strip() for k, v in contacto.items()}}
        if cliente_id is not None:
            if not re.fullmatch(r"[0-9]{11,15}", datos.get("telefono", "")):
                raise DatosInvalidos("Usá teléfono internacional, solo 11 a 15 dígitos")
            if not await self.pedidos.repo.cliente_valido(cliente_id):
                raise DatosInvalidos("El cliente no existe o está inactivo")
        items = datos.get("items", [])
        if not isinstance(items, list) or not 1 <= len(items) <= 50:
            raise DatosInvalidos("El borrador requiere entre 1 y 50 productos")
        productos = await self.pedidos.repo.productos([i["producto_id"] for i in items])
        por_id = {p["id"]: p for p in productos}
        for i in items:
            if set(i) - {"producto_id", "cantidad", "variante", "aclaraciones"}:
                raise DatosInvalidos("Solo se aceptan producto, cantidad y opciones permitidas")
            cantidad = i.get("cantidad")
            if (
                isinstance(cantidad, bool)
                or not isinstance(cantidad, int)
                or not 1 <= cantidad <= 50
            ):
                raise DatosInvalidos("La cantidad debe estar entre 1 y 50")
            p = por_id.get(i["producto_id"])
            if not p or not p["disponible"]:
                raise DatosInvalidos("Hay productos inexistentes o sin disponibilidad")
            variantes = p.get("variantes") or []
            if (
                variantes
                and i.get("variante")
                and i["variante"] not in {v["nombre"] for v in variantes}
            ):
                raise DatosInvalidos("Seleccioná una variante válida")
            if not variantes and i.get("variante"):
                raise DatosInvalidos("El producto no tiene variantes")
            await self._validar_notas(i)
        if datos.get("tipo_entrega") not in {None, "RETIRO", "DELIVERY"}:
            raise DatosInvalidos("Modalidad inválida")
        if datos.get("metodo_pago") not in {None, "EFECTIVO", "TRANSFERENCIA"}:
            raise DatosInvalidos("Método inválido")
        referencia = secrets.token_urlsafe(32)
        b = await self.repo.crear_borrador(hash_referencia(referencia), cliente_id, datos)
        mensaje = f"{SALUDO_BORRADOR} MB-{referencia}"
        return {
            "referencia": f"MB-{referencia}",
            "mensaje": mensaje,
            "url_whatsapp": (
                f"https://wa.me/{self.numero_negocio}?text={quote(mensaje)}"
                if self.numero_negocio
                else None
            ),
            "expira_en": b["expira_en"],
        }

    async def _validar_notas(self, item):
        notas = item.get("aclaraciones") or ""
        if not notas:
            return
        receta = {f["nombre"].casefold() for f in await self.repo.ingredientes(item["producto_id"])}
        canonicas = []
        for nota in notas.split(","):
            normal = nota.strip().casefold()
            ingrediente = normal.removeprefix("sin ")
            if ingrediente == "cheddar":
                ingrediente = "queso cheddar"
            elif ingrediente in {"cebolla", "bacon"}:
                opciones = (
                    {i for i in receta if i.startswith("cebolla ")}
                    if ingrediente == "cebolla"
                    else receta & {"panceta", "bacon en cubos"}
                )
                if len(opciones) == 1:
                    ingrediente = opciones.pop()
            if not normal.startswith("sin ") or ingrediente not in QUITABLES & receta:
                raise DatosInvalidos(
                    "Para WhatsApp usá solo 'Sin ingrediente' de la receta; "
                    "otras personalizaciones requieren personal"
                )
            canonicas.append("Sin " + ingrediente.capitalize())
        item["aclaraciones"] = ", ".join(dict.fromkeys(canonicas))

    async def recibir(
        self, identificador: str, telefono: str, texto: str, media_id: str | None = None,
        nombre_remitente: str | None = None,
    ):
        if not identificador or len(identificador) > 200 or len(texto) > 4096:
            raise DatosInvalidos("Mensaje inválido o demasiado largo")
        if not re.fullmatch(r"[0-9]{11,15}", telefono):
            raise DatosInvalidos("Remitente inválido")
        nombre = nombre_remitente.strip()[:120] if nombre_remitente else None
        await self.repo.recibir(identificador, telefono, texto, media_id, nombre or None)

    async def preparar(self, identificador: str) -> dict | None:
        """Etapa previa a la interpretación, en una transacción breve: texto, contexto y vínculo.

        El vínculo identifica la conversación y la versión del contexto que vio el
        intérprete; ``procesar`` lo revalida bajo bloqueo antes de aplicar la acción.
        """
        entrada = await self.repo.entrada(identificador)
        if not entrada or entrada["estado"] == "PROCESADO":
            return None
        texto = sin_referencias(entrada["texto"])
        b, _ = await self._conversacion(entrada)
        contexto = await self._contexto(b)
        return {
            "texto": texto,
            # Sin conversación la respuesta es fija: el mensaje no se envía al proveedor.
            "interpretar": b is not None and self._requiere_interpretacion(entrada, texto),
            "contexto": contexto,
            "vinculo": self._vinculo(b, contexto),
        }

    @staticmethod
    def _requiere_interpretacion(entrada, texto) -> bool:
        # Adjuntos, el saludo preparado por la web y los comandos guiados son deterministas.
        return not (entrada["media_id"] or es_saludo_borrador(texto) or es_comando_guiado(texto))

    async def _conversacion(self, entrada, bloquear=False):
        """Resuelve la conversación por teléfono y, si existe, por una única referencia."""
        referencias = referencias_en(entrada["texto"])
        if len(referencias) > 1:
            return None, "Incluí una sola referencia MB- por mensaje. No apliqué cambios."
        if not referencias and tiene_token_referencia(entrada["texto"]):
            return None, SIN_CONVERSACION
        ref = referencias.pop() if referencias else None
        b = await self.repo.conversacion(
            entrada["telefono"], hash_referencia(ref) if ref else None, bloquear=bloquear,
            nombre_remitente=entrada.get("nombre_remitente"),
        )
        return b, None if b else SIN_CONVERSACION

    async def _contexto(self, b) -> dict:
        if not b:
            return {}
        items = b["items"]
        if b["pedido_id"]:
            # Contexto sin bloqueo de larga duración ni PII; se vuelve a comprobar al aplicar.
            pedido = await self.repo.pedido(b["pedido_id"])
            items = pedido["items"]
        contexto_items = []
        for indice, item in enumerate(items, 1):
            contexto_items.append(
                {
                    "item_indice": indice,
                    "producto_id": item["producto_id"],
                    "nombre": item.get("nombre_producto", ""),
                    "cantidad": item["cantidad"],
                    "ingredientes": [
                        r["nombre"] for r in await self.repo.ingredientes(item["producto_id"])
                    ],
                }
            )
        return {"estado": b["estado"], "items": contexto_items}

    @staticmethod
    def _vinculo(b, contexto) -> dict:
        huella = hashlib.sha256(
            json.dumps(contexto, sort_keys=True, default=str).encode()
        ).hexdigest()
        return {
            "referencia_hash": b["referencia_hash"] if b else None,
            "pedido_id": b["pedido_id"] if b else None,
            "version": b["version"] if b else None,
            "huella": huella,
        }

    async def _revalidar(self, b, vinculo, reintentar) -> str | None:
        actual = self._vinculo(b, await self._contexto(b))
        if actual["referencia_hash"] != vinculo.get("referencia_hash"):
            # Otra conversación: nunca se redirige la acción a un pedido distinto.
            return CONVERSACION_CAMBIADA
        if actual != vinculo:
            if reintentar:
                raise InterpretacionDesactualizada("El pedido cambió durante la interpretación")
            return CONVERSACION_CAMBIADA
        return None

    async def procesar(
        self, identificador: str, accion: dict, vinculo: dict | None = None, reintentar=False
    ) -> str:
        """Aplica una acción con bloqueo de entrada y conversación.

        Las acciones interpretadas fuera de la transacción llegan con su ``vinculo``:
        si la conversación cambió se rechazan o, con ``reintentar``, se reinterpretan.
        """
        entrada = await self.repo.entrada(identificador, bloquear=True)
        if not entrada:
            raise NoEncontrado("El mensaje no existe")
        if entrada["estado"] == "PROCESADO":
            return entrada["respuesta"]
        texto = sin_referencias(entrada["texto"])
        b, problema = await self._conversacion(entrada, bloquear=True)
        if vinculo is not None:
            rechazo = await self._revalidar(b, vinculo, reintentar)
            if rechazo:
                mismo = b is not None and b["referencia_hash"] == vinculo.get("referencia_hash")
                await self.repo.finalizar(entrada, b if mismo else None, rechazo)
                return rechazo
        # Nunca se ejecuta una interpretación parcial de un mensaje extenso.
        largo = len(texto) > LIMITE_INTERPRETACION and self._requiere_interpretacion(
            entrada, texto
        )
        if not b:
            respuesta = (self._prefijo_derivacion("MENSAJE_LARGO") if largo else "") + problema
        elif b["pedido_id"] is None and b["expira_en"] <= datetime.now(UTC):
            respuesta = "El borrador venció. Prepará uno nuevo desde la web."
        elif entrada["media_id"]:
            if b["pedido_id"] and b["metodo_pago"] == "TRANSFERENCIA":
                await self.repo.comprobante(entrada, b["pedido_id"])
                respuesta = (
                    "Comprobante recibido. Pendiente de revisión humana; no acredita el pago."
                )
            else:
                respuesta = (
                    "No se necesita comprobante para este pedido. Primero completá el borrador."
                )
        elif largo:
            respuesta = self._prefijo_derivacion("MENSAJE_LARGO").strip()
        elif await self.repo.atencion_pendiente(b["referencia_hash"]):
            # Mientras el personal atiende, el bot no crea ni modifica el pedido.
            respuesta = EN_ATENCION
        elif accion.get("accion") == "humano" and not es_comando_guiado(texto):
            # La derivación se atiende antes de completar: nunca crea ni modifica el pedido.
            respuesta = await self._derivar(b, entrada, accion)
        elif not b["pedido_id"]:
            respuesta = await self._completar(b, accion, texto)
        else:
            respuesta = await self._operar(
                b, texto, accion, con_referencia=bool(referencias_en(entrada["texto"]))
            )
        await self.repo.finalizar(entrada, b, respuesta)
        return respuesta

    @staticmethod
    def _prefijo_derivacion(motivo) -> str:
        if motivo == "MENSAJE_LARGO":
            return (
                f"Tu mensaje supera {LIMITE_INTERPRETACION} caracteres y no lo interpreté: "
                "no apliqué cambios. Reformulalo en un mensaje más corto. "
            )
        if motivo == "PROVEEDOR":
            return "No pude interpretar tu mensaje en este momento y no apliqué cambios. "
        return ""

    async def _derivar(self, b, entrada, accion) -> str:
        motivo = accion.get("motivo")
        motivo = motivo if motivo in MOTIVOS_DERIVACION else "SOLICITUD"
        await self.repo.derivar(b["referencia_hash"], entrada["id"], motivo)
        b["estado"] = "HUMANO"
        # Una propuesta pendiente no puede confirmarse mientras atiende el personal.
        b["propuesta"] = None
        situacion = (
            "Tu pedido se conserva sin cambios."
            if b["pedido_id"]
            else "Tus datos se conservan y el pedido todavía no se registró."
        )
        return (
            self._prefijo_derivacion(motivo)
            + situacion
            + " Un empleado revisará la conversación y te responderá por este chat."
        )

    async def _completar(self, b, accion, texto=""):
        eleccion = re.fullmatch(
            r"producto\s+(\d+)\s*;\s*variante:\s*(.{1,60})", texto.strip(), flags=re.I
        )
        productos = await self.pedidos.repo.productos([i["producto_id"] for i in b["items"]])
        por_id = {p["id"]: p for p in productos}
        if eleccion and 1 <= int(eleccion[1]) <= len(b["items"]):
            item = b["items"][int(eleccion[1]) - 1]
            opciones = por_id.get(item["producto_id"], {}).get("variantes") or []
            elegida = next(
                (v["nombre"] for v in opciones if v["nombre"].casefold() == eleccion[2].casefold()),
                None,
            )
            if elegida:
                item["variante"] = elegida
        if accion.get("accion") == "datos":
            argumentos = accion.get("argumentos", {})
            for clave in ("tipo_entrega", "metodo_pago"):
                valor = str(argumentos.get(clave, "")).upper()
                if valor in (
                    {"RETIRO", "DELIVERY"}
                    if clave == "tipo_entrega"
                    else {"EFECTIVO", "TRANSFERENCIA"}
                ):
                    b[clave] = valor
            if argumentos.get("direccion") and argumentos.get("localidad"):
                b["direccion"] = {
                    "calle": str(argumentos["direccion"])[:160],
                    "numero": str(argumentos.get("numero", "S/N"))[:30],
                    "localidad": str(argumentos["localidad"])[:100],
                    "referencia": str(argumentos.get("referencias", ""))[:300],
                }
        b["estado"] = "VINCULADO"
        if not b["tipo_entrega"]:
            return "¿Retiro o delivery? Respondé 'retiro' o 'delivery'."
        if b["tipo_entrega"] == "DELIVERY" and not b["direccion"]:
            return (
                "Indicá dirección: Calle 43; número: 123; localidad: Ensenada; "
                "referencias: portón verde. Cobertura: Ensenada y Punta Lara."
            )
        if not b["metodo_pago"]:
            return "¿Efectivo o transferencia?"
        for indice, item in enumerate(b["items"], 1):
            opciones = por_id.get(item["producto_id"], {}).get("variantes") or []
            if opciones and item.get("variante") not in {v["nombre"] for v in opciones}:
                nombres = ", ".join(v["nombre"] for v in opciones)
                return f"Elegí variante para producto {indice}: {nombres}. " + (
                    f"Respondé 'producto {indice}; variante: {opciones[0]['nombre']}'."
                )
        try:
            # Revalidación completa al convertir; nunca precios del navegador o modelo.
            pedido = await self.pedidos.crear(
                cliente_id=b["cliente_id"],
                tipo_entrega=b["tipo_entrega"],
                direccion_id=None,
                direccion_nueva=b["direccion"],
                observaciones=None,
                items=[ItemNuevoPedido(**i) for i in b["items"]],
                canal="WHATSAPP",
            )
        except ErrorDominio as exc:
            return f"No pude registrar el pedido: {exc.mensaje}. Corregí los datos o pedí personal."
        b["pedido_id"] = pedido["id"]
        b["estado"] = "CREADO"
        instrucciones = "Efectivo pendiente de cobro; no envíes comprobante."
        if b["metodo_pago"] == "TRANSFERENCIA":
            instrucciones = (
                self.transferencia or "Solicitá los datos de transferencia al personal."
            ) + " Enviá el comprobante. La preparación requiere aprobación del empleado."
        return resumen(pedido) + "\n" + instrucciones

    async def _operar(self, b, texto, accion, empleado_id=None, con_referencia=False):
        pedido = await self.repo.pedido(b["pedido_id"])
        # Con varios pedidos activos, la continuación también debe nombrar el pedido.
        con_ref = " junto con la referencia MB- de este pedido" if con_referencia else ""
        pendiente = b.get("propuesta")
        aclaracion = re.fullmatch(r"producto\s+(\d+)[.!]?", texto.strip(), flags=re.I)
        if (
            pendiente
            and pendiente.get("tipo") == "ACLARACION"
            and aclaracion
            and pendiente["version"] == b["version"]
        ):
            accion = {
                "accion": pendiente["accion"]["accion"],
                "argumentos": {
                    **pendiente["accion"]["argumentos"],
                    "item_indice": int(aclaracion[1]),
                },
            }
            b["propuesta"] = None
        nombre = accion.get("accion")
        if nombre == "confirmar":
            if texto.strip(" .!¡").casefold() not in CONFIRMACIONES:
                return f"Para aceptar el nuevo total respondé 'confirmar'{con_ref}."
            propuesta = b.get("propuesta")
            if (
                not propuesta
                or propuesta.get("tipo") != "TOTAL"
                or propuesta["version"] != b["version"]
            ):
                return "No hay un cambio pendiente vigente. Volvé a solicitarlo."
            accion = propuesta["accion"]
            nombre = accion["accion"]
        else:
            propuesta = None
        if nombre not in {"quitar_ingrediente", "cantidad"}:
            return resumen(pedido) + f"\nEstado: {pedido['estado']}."
        args = accion.get("argumentos", {})
        if set(args) - {"ingrediente", "item_indice", "cantidad"}:
            return "La modificación no es válida. Pedí atención de un empleado."
        candidatos = pedido["items"]
        indice = args.get("item_indice")
        if indice is not None:
            if (
                isinstance(indice, bool)
                or not isinstance(indice, int)
                or not 1 <= indice <= len(candidatos)
            ):
                return "Indicá el número de producto que querés modificar."
            candidatos = [candidatos[indice - 1]]
        elif nombre == "quitar_ingrediente":
            ingrediente = str(args.get("ingrediente", "")).casefold()
            candidatos = [
                i
                for i in candidatos
                if ingrediente
                in {r["nombre"].casefold() for r in await self.repo.ingredientes(i["producto_id"])}
            ]
        if len(candidatos) != 1:
            b["propuesta"] = {"tipo": "ACLARACION", "version": b["version"], "accion": accion}
            listado = "; ".join(
                f"{n}: {i['nombre_producto']}" for n, i in enumerate(pedido["items"], 1)
            )
            return f"¿Cuál producto querés modificar? {listado}. Indicá 'producto N'{con_ref}."
        item = candidatos[0]
        cantidad = item["cantidad"]
        notas = item.get("aclaraciones") or ""
        if nombre == "cantidad":
            cantidad = args.get("cantidad")
            if (
                isinstance(cantidad, bool)
                or not isinstance(cantidad, int)
                or not 1 <= cantidad <= 50
            ):
                return "La cantidad debe ser un entero de 1 a 50."
        else:
            ingrediente = str(args.get("ingrediente", "")).casefold()
            receta = {
                r["nombre"].casefold() for r in await self.repo.ingredientes(item["producto_id"])
            }
            if ingrediente not in QUITABLES & receta:
                return (
                    "Ese ingrediente no se puede quitar de este producto. "
                    "Pedí atención de personal."
                )
            if f"sin {ingrediente}" in notas.casefold():
                return "El producto ya está guardado sin ese ingrediente.\n" + resumen(pedido)
            notas = re.sub(
                r"\bcon\s+" + re.escape(ingrediente) + r"\b", "", notas, flags=re.I
            ).strip(" ,;")
            if f"sin {ingrediente}" not in notas.casefold():
                notas = ", ".join(filter(None, [notas, f"Sin {ingrediente.capitalize()}"]))
        total = pedido["total"] + (cantidad - item["cantidad"]) * (
            item["precio_unitario"] + item["costo_opciones"]
        )
        if total < 0:
            return "La modificación requiere revisar los descuentos con el personal."
        anterior = {
            "item_id": item["id"],
            "cantidad": item["cantidad"],
            "aclaraciones": item["aclaraciones"],
            "total": str(pedido["total"]),
        }
        posterior = {"cantidad": cantidad, "aclaraciones": notas, "total": str(total)}
        if pedido["estado"] in {"ENTREGADO", "CANCELADO"}:
            return "El pedido está cerrado; contactá al personal."
        if (
            total != pedido["total"]
            and pedido["pagado"] == 0
            and propuesta is None
            and empleado_id is None
        ):
            b["propuesta"] = {
                "tipo": "TOTAL",
                "version": b["version"],
                "accion": accion,
                "total": str(total),
                "total_anterior": str(pedido["total"]),
            }
            return (
                f"El nuevo total sería ${total}. "
                f"Respondé 'confirmar'{con_ref} para aplicar el cambio."
            )
        if propuesta and (
            Decimal(propuesta["total"]) != total
            or Decimal(propuesta["total_anterior"]) != pedido["total"]
        ):
            b["propuesta"] = None
            return "El total cambió mientras conversábamos. Solicitá nuevamente el cambio."
        requiere_personal = pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"} or (
            total != pedido["total"] and pedido["pagado"] > 0
        )
        if requiere_personal and empleado_id is None:
            await self.repo.historial(b, accion, anterior, posterior, "PENDIENTE_EMPLEADO")
            b["estado"] = "HUMANO"
            b["propuesta"] = None
            return "El cambio requiere aprobación de un empleado. El pedido vigente se conserva."
        if nombre == "cantidad" and cantidad > item["cantidad"]:
            # La disponibilidad de venta solo limita lo que requiere insumos adicionales;
            # retirar ingredientes o reducir unidades devuelve stock ya consumido.
            productos = await self.pedidos.repo.productos([item["producto_id"]])
            if not productos or not productos[0]["disponible"]:
                return (
                    "El producto no tiene stock para agregar unidades. "
                    "Tu pedido se conserva; contactá al personal."
                )
        acumulado = sum(
            i["cantidad"]
            for i in pedido["items"]
            if i["producto_id"] == item["producto_id"]
            and i["nombre_producto"] == item["nombre_producto"]
        )
        if acumulado + cantidad - item["cantidad"] > 50:
            return "No se pueden superar 50 unidades de una misma variante."
        if (
            nombre == "quitar_ingrediente"
            and pedido["stock_consumido"]
            and pedido["estado"] in {"PENDIENTE", "CONFIRMADO"}
        ):
            await self.stock.devolver_ingrediente_antes_preparacion(
                pedido["id"], item["id"], ingrediente, usuario_id=empleado_id
            )
        if nombre == "cantidad" and pedido["stock_consumido"]:
            await self.stock.ajustar_cantidad_item(
                pedido["id"],
                item["id"],
                cantidad,
                f"version:{b['referencia_hash']}:{b['version']}",
                usuario_id=empleado_id,
            )
        await self.repo.aplicar_item(pedido, item, cantidad, notas or None)
        if (
            b["metodo_pago"] == "TRANSFERENCIA"
            and total != pedido["total"]
            and total > pedido["pagado"]
        ):
            b["estado_pago"] = "PENDIENTE"
        b["version"] += 1
        b["propuesta"] = None
        await self.repo.historial(b, accion, anterior, posterior, "APLICADO", empleado_id)
        return "Cambio guardado. Cocina recibe la versión vigente.\n" + resumen(
            await self.repo.pedido(pedido["id"])
        )

    async def revisar_comprobante(
        self, comprobante_id, aprobar, empleado_id, motivo, total_verificado=None
    ):
        comprobante = await self.repo.revision(comprobante_id)
        if not comprobante:
            raise NoEncontrado("El comprobante no existe")
        if comprobante["estado"] != "PENDIENTE":
            return {"id": comprobante["id"], "estado": comprobante["estado"]}
        pedido = await self.repo.pedido(comprobante["pedido_id"])
        if aprobar and (total_verificado is None or total_verificado != pedido["total"]):
            raise ReglaDeNegocio(
                "El importe requiere verificación del empleado. "
                "Recargá el pedido y verificá el total vigente antes de aprobar"
            )
        if pedido["estado"] in {"CANCELADO", "ENTREGADO"}:
            raise ReglaDeNegocio("El pedido está cerrado; resolver con el responsable de caja")
        if not motivo.strip():
            raise DatosInvalidos("Registrá el motivo y la verificación del importe")
        return await self.repo.revisar(comprobante, aprobar, empleado_id, motivo)

    async def revisar_cambio(
        self,
        cambio_id,
        aprobar,
        empleado_id,
        motivo,
        total_verificado=None,
        resolucion_financiera=None,
    ):
        cambio, b = await self.repo.cambio(cambio_id)
        if not cambio or not b:
            raise NoEncontrado("La solicitud de cambio no existe")
        if cambio["estado"] != "PENDIENTE_EMPLEADO":
            return {"id": cambio_id, "estado": cambio["estado"]}
        pedido = await self.repo.pedido(b["pedido_id"])
        if not motivo.strip():
            raise DatosInvalidos("Registrá cómo resolviste la solicitud con cocina")
        if aprobar:
            if cambio["version"] != b["version"]:
                raise ReglaDeNegocio("La versión cambió: revisá el pedido vigente")
            if pedido["estado"] in {"CANCELADO", "ENTREGADO"}:
                raise ReglaDeNegocio("El pedido está cerrado")
            if Decimal(cambio["anterior"]["total"]) != pedido["total"]:
                raise ReglaDeNegocio(
                    "El importe del pedido cambió: solicitá nuevamente la revisión"
                )
            nuevo_total = Decimal(cambio["posterior"]["total"])
            if nuevo_total != pedido["total"]:
                if total_verificado != nuevo_total or resolucion_financiera != "COBRO_PENDIENTE":
                    raise ReglaDeNegocio(
                        "El empleado debe aceptar el nuevo importe y coordinar "
                        "el saldo o devolución con caja"
                    )
                if pedido["pagado"] > nuevo_total:
                    raise ReglaDeNegocio(
                        "Antes de aprobar, registrá en pagos la devolución de "
                        f"${pedido['pagado']-nuevo_total} con su motivo"
                    )
            respuesta = await self._operar(b, "", cambio["accion"], empleado_id)
            if not respuesta.startswith("Cambio guardado"):
                raise ReglaDeNegocio(respuesta)
            b["estado"] = "CREADO"
            if nuevo_total > pedido["pagado"]:
                if b["metodo_pago"] == "TRANSFERENCIA":
                    b["estado_pago"] = "PENDIENTE"
                respuesta += f"\nSaldo pendiente de cobro: ${nuevo_total-pedido['pagado']}."
        else:
            respuesta = f"El personal rechazó el cambio del pedido #{pedido['numero']}. " + motivo
            b["estado"] = "CREADO"
        estado = "APLICADO" if aprobar else "RECHAZADO"
        await self.repo.cerrar_cambio(cambio_id, estado, empleado_id, motivo)
        await self.repo.actualizar_borrador(b)
        await self.repo.encolar(f"cambio-revision:{cambio_id}", b["telefono"], respuesta)
        return {"id": cambio_id, "estado": estado}

    async def responder_atencion(self, atencion_id, empleado_id, texto, solicitud_id):
        """Encola una respuesta del personal; el envío real lo informa la outbox."""
        texto = texto.strip() if isinstance(texto, str) else ""
        if not 1 <= len(texto) <= 1000:
            raise DatosInvalidos("Escribí una respuesta de 1 a 1000 caracteres")
        if not isinstance(solicitud_id, str) or not UUID.fullmatch(solicitud_id):
            raise DatosInvalidos("La solicitud de respuesta no es válida")
        atencion = await self.repo.atencion(atencion_id, bloquear=True)
        if not atencion:
            raise NoEncontrado("La atención no existe")
        clave = f"atencion:{atencion_id}:{solicitud_id}"
        # Un reintento de la misma solicitud devuelve la salida existente sin duplicarla.
        existente = await self.repo.respuesta_atencion(clave)
        if existente:
            return existente
        if atencion["estado"] != "PENDIENTE":
            raise ReglaDeNegocio("La atención ya fue resuelta; no se envían nuevas respuestas")
        return await self.repo.encolar_respuesta(clave, atencion, texto, empleado_id)

    async def resolver_atencion(self, atencion_id, empleado_id, resolucion):
        resolucion = resolucion.strip() if isinstance(resolucion, str) else ""
        if not 1 <= len(resolucion) <= 500:
            raise DatosInvalidos("Registrá cómo resolviste la atención (hasta 500 caracteres)")
        atencion = await self.repo.atencion(atencion_id, bloquear=True)
        if not atencion:
            raise NoEncontrado("La atención no existe")
        if atencion["estado"] == "PENDIENTE":
            await self.repo.resolver_atencion(atencion, empleado_id, resolucion)
        return {"id": atencion_id, "estado": "RESUELTA"}
