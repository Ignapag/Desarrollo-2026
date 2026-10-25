"""Orquestación del bot: la interpretación propone; estas reglas deciden."""

from __future__ import annotations

import base64
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
from app.modules.whatsapp.application.conversacion import resolver_conversacion
from app.modules.whatsapp.application.edicion_conversacional import (
    ACCIONES_ITEMS,
    AYUDA,
    catalogo,
    comando_guiado,
    editar_productos,
    es_modificacion,
    requiere_personal,
)
from app.modules.whatsapp.application.edicion_multiple import editar_multiples
from app.modules.whatsapp.domain.memoria import (
    CAMPOS_DATOS,
    PREGUNTAS,
    pregunta_actual,
    resumir_turno,
)
from app.modules.whatsapp.domain.mensajes import (
    LIMITE_INTERPRETACION,
    SALUDO_BORRADOR,
    es_comando_guiado,
    es_saludo_borrador,
    hash_referencia,
    huella_inicio,
    resumen,
    sin_referencias,
    sin_selector_pedido,
)
from app.modules.whatsapp.domain.textos import (
    dinero,
    estado_pedido,
    instrucciones_pago,
    mensaje_web,
)


class RepositorioBot(Protocol):
    async def memoria(self, telefono, referencia_hash) -> list[dict]: ...
    async def recuperar_proveedor(self, b) -> bool: ...
    async def atencion_humana(self, referencia_hash) -> bool: ...
    async def sesion(self, telefono, bloquear=False) -> dict | None: ...
    async def conversaciones(self, telefono) -> list[dict]: ...
    async def guardar_contexto(self, entrada, b) -> None: ...
    async def crear_borrador(self, referencia_hash, cliente_id, datos) -> dict: ...
    async def recibir(
        self, identificador, telefono, texto, media_id, nombre_remitente=None
    ) -> None: ...
    async def entrada(self, identificador, bloquear=False) -> dict | None: ...
    async def conversacion(
        self, telefono, referencia_hash=None, bloquear=False, nombre_remitente=None,
        inicio_hash=None, numero_pedido=None,
    ) -> dict | None: ...
    async def finalizar(self, entrada, b, respuesta) -> None: ...
    async def pedido(self, pedido_id) -> dict: ...
    async def cotizar_operacion(self, pedido, cambios) -> Decimal: ...
    async def refrescar_operacion(self, b) -> None: ...
    async def ingredientes(self, producto_id) -> list[dict]: ...
    async def ingredientes_snapshot(self, receta_snapshot) -> list[dict]: ...
    async def ingredientes_items(self, items) -> list[list[dict]]: ...
    async def direccion_pedido(self, pedido) -> dict | None: ...
    async def historial(self, b, accion, anterior, posterior, estado, empleado_id=None) -> dict: ...
    async def aplicar_item(
        self, pedido, item, cantidad, aclaraciones, empleado_id=None,
    ) -> None: ...
    async def comprobante(self, entrada, pedido_id) -> None: ...
    async def revision(self, comprobante_id) -> dict | None: ...
    async def revisar(self, comprobante, aprobar, empleado_id, motivo) -> dict: ...
    async def cambio(self, cambio_id) -> tuple[dict | None, dict | None]: ...
    async def cerrar_cambio(self, cambio_id, estado, empleado_id, motivo) -> None: ...
    async def actualizar_borrador(self, b) -> None: ...
    async def encolar(self, clave, telefono, texto) -> None: ...
    async def derivar(self, referencia_hash, entrada_id, motivo) -> None: ...
    async def derivar_general(self, entrada_id, motivo) -> None: ...
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
    "💬 Un empleado está atendiendo tu consulta. Tu pedido sigue sin cambios."
)
CONVERSACION_CAMBIADA = (
    "💬 Tu pedido cambió mientras revisábamos el mensaje y no apliqué cambios nuevos. "
    "¿Me repetís lo que necesitás? Así seguimos con el pedido correcto."
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def momento_preparacion():
    return datetime.now(UTC)


class ServicioBot:
    def __init__(
        self,
        repo: RepositorioBot,
        pedidos: ServicioPedidos,
        numero_negocio: str = "",
        transferencia: str = "",
        stock: ServicioStock | None = None,
        productos=None,
    ):
        self.repo = repo
        self.pedidos = pedidos
        self.numero_negocio = numero_negocio
        self.transferencia = transferencia
        self.stock = stock
        self.productos = productos
        self.quitables = QUITABLES

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
        if contacto is not None and cliente_id is None:
            try:
                mensaje = mensaje_web(datos, productos, momento_preparacion())
            except ValueError as exc:
                raise DatosInvalidos(
                    "El pedido es muy largo para WhatsApp. Dividilo en dos pedidos."
                ) from exc
            huella = huella_inicio(contacto["telefono"], mensaje)
            # Identificador interno compatible con el contrato anterior; no viaja en el chat
            # ni permite reclamar este borrador. La identidad viene del webhook firmado.
            referencia = base64.urlsafe_b64encode(bytes.fromhex(huella)).decode().rstrip("=")
            datos = {**datos, "inicio_hash": huella}
        else:
            # Compatibilidad con borradores internos o clientes web anteriores sin contacto.
            referencia = secrets.token_urlsafe(32)
            mensaje = f"{SALUDO_BORRADOR} MB-{referencia}"
        b = await self.repo.crear_borrador(hash_referencia(referencia), cliente_id, datos)
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

    async def _ingredientes_item(self, item):
        if item.get("receta_snapshot") is not None:
            return await self.repo.ingredientes_snapshot(item["receta_snapshot"])
        return await self.repo.ingredientes(item["producto_id"])

    async def _validar_notas(self, item):
        notas = item.get("aclaraciones") or ""
        if not notas:
            return
        receta = {f["nombre"].casefold() for f in await self._ingredientes_item(item)}
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
        b, _ = await self._conversacion(entrada)
        texto = sin_selector_pedido(sin_referencias(entrada["texto"]))
        interpretar = (
            b is not None and not await self.repo.atencion_humana(b["referencia_hash"])
            and not self._solicita_personal(texto)
            and await self._requiere_interpretacion(entrada, texto, b)
        )
        contexto = await self._contexto(b, para_ia=interpretar)
        vinculo = {**self._vinculo(b, contexto, entrada), "contexto_ia": interpretar}
        return {
            "texto": texto,
            # Sin conversación la respuesta es fija: el mensaje no se envía al proveedor.
            "interpretar": interpretar,
            "contexto": contexto,
            "vinculo": vinculo,
        }

    async def _es_eleccion_variante(self, b, texto):
        if not b or b["pedido_id"] or len(texto) > 60:
            return False
        productos = await self.pedidos.repo.productos([i["producto_id"] for i in b["items"]])
        por_id = {p["id"]: p for p in productos}
        for item in b["items"]:
            opciones = por_id.get(item["producto_id"], {}).get("variantes") or []
            if opciones and item.get("variante") not in {v["nombre"] for v in opciones}:
                return texto.strip(" .!¡").casefold() in {v["nombre"].casefold() for v in opciones}
        return False

    async def _requiere_interpretacion(self, entrada, texto, b=None) -> bool:
        # Adjuntos, el saludo preparado por la web y los comandos guiados son deterministas.
        inicio = b and b.get("inicio_hash") == huella_inicio(entrada["telefono"], entrada["texto"])
        if (
            inicio or entrada.get("_eleccion") or entrada["media_id"] or comando_guiado(texto, b)
            or es_saludo_borrador(texto) or es_comando_guiado(texto)
        ):
            return False
        return not await self._es_eleccion_variante(b, texto)

    async def _conversacion(self, entrada, bloquear=False):
        return await resolver_conversacion(self.repo, entrada, bloquear)

    @staticmethod
    def _vencido(b):
        return b is not None and not b["pedido_id"] and b["expira_en"] <= datetime.now(UTC)

    @staticmethod
    def _solicita_personal(texto):
        texto = texto.casefold().strip(" .!¡?¿")
        persona = r"(?:emplead[oa]|persona|human[oa]|encargad[oa]|asesor[a]?)"
        if re.fullmatch(r"(?:(?:un|una|el|la)\s+)?" + persona, texto):
            return True
        if re.search(r"\bno\s+(?:quiero|necesito|deseo)\b", texto):
            return False
        destino = r"(?:(?:un|una|el|la)\s+)?" + persona
        # Reconocer la petición, no palabras sueltas en nombres o resúmenes web.
        return bool(re.search(
            r"\b(?:"
            r"(?:hablar|comunicarme|contactar)(?:\s+(?:con|a))?\s+" + destino
            + r"|(?:quiero|necesito|deseo|atienda)\s+" + destino
            + r"|atenci[oó]n\s+(?:" + persona + r"|de\s+" + destino + r"))\b", texto
        ))

    async def _registrar_general(self, entrada, motivo):
        # El destino sale del remitente verificado, nunca de datos del carrito o la IA.
        await self.repo.derivar_general(entrada["id"], motivo)
        respuesta = (
            "📎 ¡Comprobante recibido! Un empleado va a revisarlo y te responderá por acá. "
            "El pago todavía no está confirmado."
            if motivo == "COMPROBANTE" else
            "💬 Le pasamos tu solicitud a un empleado. Te responderá por acá."
        )
        await self.repo.finalizar(entrada, None, respuesta)
        return respuesta

    async def _contexto(self, b, *, para_ia=True) -> dict:
        if not b:
            return {}
        items = b["items"]
        estado_pedido_actual = None
        operacion = None
        if b["pedido_id"]:
            # Contexto sin bloqueo de larga duración ni PII; se vuelve a comprobar al aplicar.
            pedido = await self.repo.pedido(b["pedido_id"])
            items = pedido["items"]
            estado_pedido_actual = pedido["estado"]
            operacion = self._foto_operacion(pedido)
        if not para_ia:
            # Los comandos explícitos se resuelven nuevamente bajo bloqueo. Su vínculo
            # sigue comprobando foco, versión, composición, fondos y reparto vigentes,
            # sin construir catálogo, recetas ni historial que no irá a un proveedor.
            return {"estado": b["estado"], "operacion": operacion, "composicion": items}
        contexto_items = []
        recetas = await self.repo.ingredientes_items(items)
        for indice, item in enumerate(items, 1):
            ingredientes = [r["nombre"] for r in recetas[indice - 1]]
            # El contexto sólo lleva nombres conocidos de receta, nunca notas libres.
            notas = {n.strip().casefold() for n in (item.get("aclaraciones") or "").split(",")}
            contexto_items.append(
                {
                    "item_indice": indice,
                    "producto_id": item["producto_id"],
                    "nombre": item.get("nombre_producto", ""),
                    "cantidad": item["cantidad"],
                    "variante": item.get("variante"),
                    "ingredientes": ingredientes,
                    "ingredientes_retirados": [
                        n for n in ingredientes if "sin " + n.casefold() in notas
                    ],
                }
            )
        chat = b.get("contexto_chat") or {}
        return {
            "estado": b["estado"], "estado_pedido": estado_pedido_actual,
            "tipo_entrega": pedido["tipo_entrega"] if operacion else b["tipo_entrega"],
            "metodo_pago": pedido["metodo_pago_acordado"] if operacion else b["metodo_pago"],
            "operacion": operacion,
            "items": contexto_items,
            "catalogo": [
                {"id": p["id"], "nombre": p["nombre"], "descripcion": p.get("descripcion"),
                 "variantes": p.get("variantes") or [],
                 "ingredientes": p.get("ingredientes_quitables") or []}
                for p in await catalogo(self)
            ],
            "edicion_pendiente": {
                k: v for k, v in (chat.get("edicion") or {}).items()
                if k in {"accion", "argumentos", "datos_presentes", "pregunta_producto"}
            },
            "conversacion": {
                "solicitud_pendiente": pregunta_actual(b),
                "datos_presentes": sorted(set(chat.get("datos", {})) & CAMPOS_DATOS),
                "ultimos_turnos": await self.repo.memoria(b["telefono"], b["referencia_hash"]),
            },
        }

    @staticmethod
    def _vinculo(b, contexto, entrada=None) -> dict:
        huella = hashlib.sha256(
            json.dumps(contexto, sort_keys=True, default=str).encode()
        ).hexdigest()
        return {
            "referencia_hash": b["referencia_hash"] if b else None,
            "pedido_id": b["pedido_id"] if b else None,
            "version": b["version"] if b else None,
            "huella": huella,
            "solicitud_id": (entrada or {}).get("_solicitud_id"),
            "sesion_version": (entrada or {}).get("_sesion_version"),
        }

    async def _revalidar(self, b, vinculo, reintentar, entrada=None) -> str | None:
        para_ia = vinculo.get("contexto_ia", True)
        actual = self._vinculo(b, await self._contexto(b, para_ia=para_ia), entrada)
        if "contexto_ia" in vinculo:
            actual["contexto_ia"] = para_ia
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
        solicita_personal = self._solicita_personal(entrada["texto"])
        if entrada["media_id"] or solicita_personal:
            # La lectura previa evita reclamar un carrito o crear un cliente sólo
            # para recibir un adjunto o atender una consulta sin compra vigente.
            previa, _ = await self._conversacion(entrada)
            if entrada["media_id"] and (
                not previa or not previa["pedido_id"] or previa["metodo_pago"] != "TRANSFERENCIA"
            ):
                return await self._registrar_general(entrada, "COMPROBANTE")
            if solicita_personal and (not previa or self._vencido(previa)):
                return await self._registrar_general(entrada, "SOLICITUD")
        b, problema = await self._conversacion(entrada, bloquear=True)
        texto = sin_selector_pedido(sin_referencias(entrada["texto"]))
        guiada = comando_guiado(texto, b)
        if (guiada and accion.get("accion") in {None, "consulta", "humano", "confirmar"}
                and not entrada["media_id"]):
            accion = guiada
        if vinculo is not None:
            # Si cocina ganó la carrera, conservar la solicitud original y derivarla;
            # nunca volver a interpretar contra una compra que ya comenzó a prepararse.
            if b and b["pedido_id"] and es_modificacion(accion, b) and (
                b["referencia_hash"] == vinculo.get("referencia_hash")
            ) and ((p := await self.repo.pedido(b["pedido_id"])).get("preparacion_en")
                or p["estado"] in {"EN_PREPARACION", "LISTO"}):
                respuesta = await self._derivar_modificacion(b, entrada, accion)
                await self.repo.finalizar(entrada, b, respuesta)
                return respuesta
            rechazo = await self._revalidar(b, vinculo, reintentar, entrada)
            if rechazo:
                mismo = b is not None and b["referencia_hash"] == vinculo.get("referencia_hash")
                await self.repo.finalizar(entrada, b if mismo else None, rechazo)
                return rechazo
        if entrada["media_id"] and (
            not b or not b["pedido_id"] or b["metodo_pago"] != "TRANSFERENCIA"
            or (await self.repo.pedido(b["pedido_id"]))["estado"] in {"ENTREGADO", "CANCELADO"}
        ):
            return await self._registrar_general(entrada, "COMPROBANTE")
        if (
            b and solicita_personal and not entrada["media_id"] and not self._vencido(b)
            and not es_comando_guiado(texto) and not await self._es_eleccion_variante(b, texto)
        ):
            # Pedir personal es una decisión explícita, independiente del intérprete.
            accion = {"accion": "humano", "motivo": "SOLICITUD"}
        fallo_proveedor = accion.get("motivo") == "PROVEEDOR"
        if b and not fallo_proveedor and not entrada["media_id"]:
            await self.repo.recuperar_proveedor(b)
        # Nunca se ejecuta una interpretación parcial de un mensaje extenso.
        largo = len(texto) > LIMITE_INTERPRETACION and await self._requiere_interpretacion(
            entrada, texto, b
        )
        if not b:
            respuesta = (self._prefijo_derivacion("MENSAJE_LARGO") if largo else "") + problema
        elif b["pedido_id"] is None and b["expira_en"] <= datetime.now(UTC):
            respuesta = (
                "⏳ El resumen del pedido venció. Volvé a prepararlo desde la web "
                "y mandalo por acá."
            )
        elif entrada["media_id"]:
            if b["pedido_id"] and b["metodo_pago"] == "TRANSFERENCIA":
                await self.repo.comprobante(
                    {**entrada, "id": entrada.get("_solicitud_id", entrada["id"])}, b["pedido_id"]
                )
                respuesta = (
                    "📎 ¡Comprobante recibido! Un empleado va a revisar la transferencia. "
                    "Te avisamos por acá cuando el pago esté confirmado. 💚"
                )
            else:
                respuesta = (
                    "💬 Por ahora no hace falta un comprobante. Si pagás en efectivo, "
                    "lo abonás al recibir el pedido. Si todavía no lo registramos, "
                    "mandanos primero el resumen preparado desde la web."
                )
        elif largo:
            respuesta = self._prefijo_derivacion("MENSAJE_LARGO").strip()
        elif fallo_proveedor and not await self.repo.atencion_humana(b["referencia_hash"]):
            respuesta = await self._derivar(b, entrada, {"accion": "humano", "motivo": "PROVEEDOR"})
        elif await self.repo.atencion_pendiente(b["referencia_hash"]):
            # Mientras el personal atiende, el bot no crea ni modifica el pedido.
            if accion.get("accion") == "datos":
                self._recoger_datos(b, accion, entrada)
            respuesta = EN_ATENCION
        elif fallo_proveedor:
            respuesta = self._prefijo_derivacion("PROVEEDOR").strip()
        elif b["pedido_id"] and es_modificacion(accion, b) and requiere_personal(
            await self.repo.pedido(b["pedido_id"])
        ):
            respuesta = await self._derivar_modificacion(b, entrada, accion)
        elif accion.get("accion") == "ayuda":
            respuesta = AYUDA
        elif accion.get("accion") == "preguntar":
            campo = (accion.get("argumentos") or {}).get("campo")
            respuesta = self._preguntar(b, campo, entrada)
        elif accion.get("accion") == "humano" and not (
            es_comando_guiado(texto) or await self._es_eleccion_variante(b, texto)
        ):
            # La derivación se atiende antes de completar: nunca crea ni modifica el pedido.
            respuesta = await self._derivar(
                b, {**entrada, "id": entrada.get("_solicitud_id", entrada["id"])}, accion
            )
        elif accion.get("accion") == "editar_pedido" and not b["pedido_id"]:
            respuesta = "💬 Completá primero el pedido del carrito para poder modificarlo."
        elif not b["pedido_id"]:
            respuesta = self._recoger_datos(b, accion, entrada)
            if respuesta is None:
                respuesta = await self._completar(b, accion, texto)
        elif accion.get("accion") == "editar_pedido" or (
            (b.get("contexto_chat") or {}).get("multiple")
            and accion.get("accion") in (ACCIONES_ITEMS - {"cancelar"})
            | {"datos", "preguntar", "confirmar"}
        ) or (accion.get("accion") == "confirmar"
              and (b.get("propuesta") or {}).get("tipo") == "MULTIPLE"):
            respuesta = await editar_multiples(self, b, {**entrada, "texto": texto}, accion)
        elif accion.get("accion") in ACCIONES_ITEMS or (
            accion.get("accion") == "confirmar" and (b.get("propuesta") or {}).get("tipo")
            in {"COMPOSICION", "CANCELACION"}
        ):
            if accion.get("accion") != "completar_edicion" and (
                b.get("contexto_chat") or {}
            ).get("datos"):
                self._limpiar_solicitud(b)
                b["version"] += 1
            respuesta = await editar_productos(self, b, {**entrada, "texto": texto}, accion)
        elif accion.get("accion") == "datos":
            respuesta = self._recoger_datos(b, accion, entrada)
            if respuesta is None:
                respuesta = await self._operar_datos(b, entrada)
        else:
            if accion.get("accion") in {"cantidad", "quitar_ingrediente"}:
                if (b.get("contexto_chat") or {}).get("datos"):
                    self._limpiar_solicitud(b)
                    b["version"] += 1
                else:
                    self._marcar_pregunta(b, None)
            respuesta = await self._operar(b, texto, accion)
        if b:
            entrada["_memoria_ia"] = resumir_turno(accion, b, QUITABLES)
        await self.repo.guardar_contexto(entrada, b)
        await self.repo.finalizar(entrada, b, respuesta)
        return respuesta

    @staticmethod
    def _prefijo_derivacion(motivo) -> str:
        if motivo == "MENSAJE_LARGO":
            return (
                f"💬 Tu mensaje supera {LIMITE_INTERPRETACION} caracteres. "
                "¿Podés mandarlo en uno más corto? Tu pedido sigue sin cambios. "
            )
        if motivo == "PROVEEDOR":
            return (
                "💬 El asistente de IA no está disponible en este momento. "
                "Tu pedido y tu mensaje se conservan. Escribí *ayuda* para continuar "
                "con opciones guiadas, *resumen* para consultar "
                "o *empleado* para atención personal. "
            )
        return ""

    def _preguntar(self, b, campo, entrada):
        if campo not in PREGUNTAS:
            return PREGUNTAS["consulta"]
        anterior = b.get("contexto_chat") or {}
        chat = dict(anterior)
        if campo == "direccion" or (b["pedido_id"] and campo in {"entrega", "pago"}):
            chat["datos"] = {}
            chat["solicitud_id"] = entrada.get("_solicitud_id", entrada["id"])
        chat["pregunta"] = campo
        if chat != anterior:
            b["contexto_chat"] = chat
            b["version"] += 1
        return PREGUNTAS[campo]

    @staticmethod
    def _foto_operacion(pedido):
        return {
            campo: str(pedido.get(campo)) for campo in (
                "version", "estado", "tipo_entrega", "direccion_id", "metodo_pago_acordado",
                "total", "pagado", "asignado", "envio_id", "estado_envio", "fondos",
                "preparacion_en",
            )
        }

    @staticmethod
    def _limpiar_solicitud(b):
        b["contexto_chat"] = {"pregunta": None}
        b["propuesta"] = None

    async def _operar_datos(self, b, entrada, propuesta=None):
        pedido = await self.repo.pedido(b["pedido_id"])
        chat = b.get("contexto_chat") or {}
        datos = chat.get("datos") or {}
        cambios = {}
        for campo, destino, permitidos in (
            ("tipo_entrega", "tipo_entrega", {"RETIRO", "DELIVERY"}),
            ("metodo_pago", "metodo_pago_acordado", {"EFECTIVO", "TRANSFERENCIA"}),
        ):
            if campo in datos:
                valor = str(datos[campo]).upper()
                if valor not in permitidos:
                    return "💬 Elegí retiro o delivery, y efectivo o transferencia."
                cambios[destino] = valor
        if datos.get("direccion"):
            cambios["direccion_nueva"] = {
                "calle": datos["direccion"], "numero": datos["numero"],
                "localidad": datos["localidad"], "referencia": datos.get("referencias", ""),
            }
            # Una dirección de entrega indica que desea recibirlo por delivery.
            cambios.setdefault("tipo_entrega", "DELIVERY")
        elif "referencias" in datos:
            direccion = await self.repo.direccion_pedido(pedido)
            if direccion:
                cambios["direccion_nueva"] = {**direccion, "referencia": datos["referencias"]}
            else:
                return (
                    "💬 El pedido es para retiro. Para dejar referencias de entrega, "
                    "elegí *delivery* y completá la dirección."
                )
        if not cambios:
            return "💬 Contame qué dato del pedido querés cambiar."
        foto = self._foto_operacion(pedido)
        if requiere_personal(pedido):
            chat["bloqueo_operativo"] = (
                "Coordinar la desasignación con reparto antes de editar los datos del pedido."
                if pedido.get("asignado") else
                "El pedido está en camino o cerrado: requiere corrección coordinada del personal."
            )
            origen = chat.get("solicitud_id") or entrada["id"]
            return await self._derivar(b, {**entrada, "id": origen}, {"accion": "humano"})
        if propuesta and propuesta.get("operacion") != foto:
            self._limpiar_solicitud(b)
            return CONVERSACION_CAMBIADA
        if cambios.get("tipo_entrega", pedido["tipo_entrega"]) == "DELIVERY" and not (
            cambios.get("direccion_nueva") or pedido.get("direccion_id")
        ):
            chat["pregunta"] = "direccion"
            return PREGUNTAS["direccion"]
        try:
            total = await self.repo.cotizar_operacion(pedido, cambios)
            if total < pedido["pagado"]:
                chat["bloqueo_operativo"] = (
                    "Coordinar la devolución en caja antes de reducir el total "
                    "por debajo del neto cobrado."
                )
                origen = chat.get("solicitud_id") or entrada["id"]
                return await self._derivar(b, {**entrada, "id": origen}, {"accion": "humano"})
            if total != pedido["total"] and propuesta is None:
                b["propuesta"] = {
                    "tipo": "TOTAL", "operativa": True, "version": b["version"],
                    "operacion": foto, "total": str(total), "cambios": cambios,
                }
                return (
                    f"💰 El nuevo total sería *{dinero(total)}*.\n"
                    "Respondé *confirmar* para aplicar el cambio."
                )
            if propuesta and Decimal(propuesta["total"]) != total:
                self._limpiar_solicitud(b)
                return "💬 El total cambió mientras conversábamos. ¿Me repetís el cambio?"
            await self.pedidos.editar_operacion(
                pedido["id"], cambios=cambios, usuario_id=None,
                motivo="Corrección solicitada por el cliente en WhatsApp",
                version_esperada=pedido["version"], origen="WHATSAPP",
            )
        except ErrorDominio as exc:
            self._limpiar_solicitud(b)
            return f"💬 No pude aplicar el cambio: {exc.mensaje}. Tu pedido sigue sin cambios."
        # El comando canónico también actualiza el borrador: no sobrescribirlo con la copia vieja.
        await self.repo.refrescar_operacion(b)
        self._limpiar_solicitud(b)
        b["version"] += 1
        return "✅ Cambio guardado.\n\n" + resumen(await self.repo.pedido(pedido["id"]))

    @staticmethod
    def _marcar_pregunta(b, campo):
        chat = dict(b.get("contexto_chat") or {})
        if chat.get("pregunta") != campo:
            chat["pregunta"] = campo
            b["contexto_chat"] = chat
            b["version"] += 1

    def _recoger_datos(self, b, accion, entrada):
        if accion.get("accion") != "datos":
            return None
        args = accion.get("argumentos") or {}
        chat = dict(b.get("contexto_chat") or {})
        datos = dict(chat.get("datos") or {})
        limites = {"direccion": 160, "numero": 30, "localidad": 100, "referencias": 300}
        for campo in CAMPOS_DATOS:
            if isinstance(args.get(campo), str) and 1 <= len(args[campo].strip()) <= limites.get(
                campo, 30
            ):
                datos[campo] = args[campo].strip()
        if str(args.get("tipo_entrega", "")).upper() == "RETIRO":
            for campo in ("direccion", "numero", "localidad", "referencias"):
                datos.pop(campo, None)
        if not datos:
            return None
        chat.update(datos=datos)
        chat.setdefault("solicitud_id", entrada.get("_solicitud_id", entrada["id"]))
        b["contexto_chat"] = chat
        b["version"] += 1
        if not b["pedido_id"]:
            b["estado"] = "VINCULADO"
            for campo, permitidos in (
                ("tipo_entrega", {"RETIRO", "DELIVERY"}),
                ("metodo_pago", {"EFECTIVO", "TRANSFERENCIA"}),
            ):
                if str(datos.get(campo, "")).upper() in permitidos:
                    b[campo] = datos[campo].upper()
        # Los valores permanecen en el servidor; Gemini solo recibe los campos presentes.
        if set(datos) & {"direccion", "numero", "localidad"} or (
            "referencias" in datos and not b["pedido_id"]
        ):
            for campo in ("direccion", "numero", "localidad"):
                if not datos.get(campo):
                    chat["pregunta"] = campo
                    return PREGUNTAS[campo]
            if datos["localidad"].casefold() not in {"ensenada", "punta lara"}:
                datos.pop("localidad")
                chat["pregunta"] = "localidad"
                return "📍 Por ahora llegamos a Ensenada y Punta Lara. ¿En cuál es la entrega?"
            if not b["pedido_id"]:
                b["direccion"] = {
                    "calle": datos["direccion"], "numero": datos["numero"],
                    "localidad": datos["localidad"], "referencia": datos.get("referencias", ""),
                }
        chat["pregunta"] = None
        return None

    async def _derivar(self, b, entrada, accion) -> str:
        motivo = accion.get("motivo")
        motivo = motivo if motivo in MOTIVOS_DERIVACION else "SOLICITUD"
        await self.repo.derivar(b["referencia_hash"], entrada["id"], motivo)
        b["estado"] = "HUMANO"
        # Un incidente técnico puede retomarse con comandos guiados, conservando
        # su propuesta. La atención humana explícita sí invalida la confirmación.
        if motivo != "PROVEEDOR":
            b["propuesta"] = None
        situacion = (
            "Tu pedido se conserva sin cambios."
            if b["pedido_id"]
            else "Tus datos se conservan y el pedido todavía no se registró."
        )
        return (
            self._prefijo_derivacion(motivo)
            + situacion
            + " Un empleado va a revisar tu consulta y te responderá por acá. 💚"
        )

    async def _derivar_modificacion(self, b, entrada, accion):
        pedido = await self.repo.pedido(b["pedido_id"])
        if accion.get("accion") == "datos":
            self._recoger_datos(b, accion, entrada)
        elif accion.get("accion") == "preguntar":
            self._preguntar(b, (accion.get("argumentos") or {}).get("campo"), entrada)
        chat = dict(b.get("contexto_chat") or {})
        chat["bloqueo_operativo"] = (
            "Coordinar la desasignación con reparto antes de modificar el pedido."
            if pedido.get("asignado") else
            "La preparación ya comenzó o el pedido está cerrado: coordinar con el personal."
        )
        b["contexto_chat"] = chat
        if accion.get("accion") in {"cantidad", "quitar_ingrediente"}:
            # Mantener la revisión de cocina que ya ofrece la bandeja para estos comandos.
            await self._operar(b, entrada["texto"], {**accion, "entrada_id": entrada["id"]})
        respuesta = await self._derivar(b, entrada, {"accion": "humano"})
        return "👨‍🍳 El cambio requiere aprobación de un empleado. " + respuesta

    async def _completar(self, b, accion, texto=""):
        eleccion = re.fullmatch(
            r"producto\s+(\d+)\s*;\s*variante:\s*(.{1,60})", texto.strip(), flags=re.I
        )
        productos = await self.pedidos.repo.productos([i["producto_id"] for i in b["items"]])
        por_id = {p["id"]: p for p in productos}
        # La respuesta a la pregunta de variante puede ser simplemente «Doble».
        if not eleccion:
            for item in b["items"]:
                opciones = por_id.get(item["producto_id"], {}).get("variantes") or []
                if opciones and item.get("variante") not in {v["nombre"] for v in opciones}:
                    elegida = next(
                        (v["nombre"] for v in opciones
                         if v["nombre"].casefold() == texto.strip(" .!¡").casefold()), None
                    )
                    if elegida:
                        item["variante"] = elegida
                    break
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
            argumentos = {
                **(b.get("contexto_chat") or {}).get("datos", {}),
                **accion.get("argumentos", {}),
            }
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
            self._marcar_pregunta(b, "entrega")
            return "🛍️ ¿Retiro o delivery? Contame si pasás por el local o te lo llevamos. 🛵"
        if b["tipo_entrega"] == "DELIVERY" and not b["direccion"]:
            self._marcar_pregunta(b, "direccion")
            return (
                "📍 ¿A qué dirección te lo llevamos? Pasanos calle, número y localidad "
                "(Ensenada o Punta Lara). Si hay alguna referencia para encontrarte, sumala. 😊"
            )
        if not b["metodo_pago"]:
            self._marcar_pregunta(b, "pago")
            return "💵 ¿Preferís pagar en efectivo o por transferencia? 🏦"
        for item in b["items"]:
            opciones = por_id.get(item["producto_id"], {}).get("variantes") or []
            if opciones and item.get("variante") not in {v["nombre"] for v in opciones}:
                self._marcar_pregunta(b, "variante")
                nombres = ", ".join(v["nombre"] for v in opciones)
                nombre = por_id.get(item["producto_id"], {}).get("nombre", "hamburguesa")
                return f"🍔 ¿Cómo querés tu {nombre}? Opciones: *{nombres}*. " + (
                    f"Podés responder, por ejemplo, *{opciones[0]['nombre']}*."
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
                metodo_pago_acordado=b["metodo_pago"],
            )
        except ErrorDominio as exc:
            return (
                f"💬 No pude registrar el pedido: {exc.mensaje}. "
                "Escribinos y te ayudamos a resolverlo."
            )
        b["pedido_id"] = pedido["id"]
        b["estado"] = "CREADO"
        self._limpiar_solicitud(b)
        instrucciones = instrucciones_pago(b["metodo_pago"], self.transferencia, b["tipo_entrega"])
        return (
            "✅ ¡Recibimos tu pedido!\n\n" + resumen(pedido) + "\n\n" + instrucciones
        )

    async def _operar(self, b, texto, accion, empleado_id=None):
        pedido = await self.repo.pedido(b["pedido_id"])
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
                return "💬 Para aceptar el nuevo total respondé *confirmar*."
            propuesta = b.get("propuesta")
            if (
                not propuesta
                or propuesta.get("tipo") != "TOTAL"
                or propuesta["version"] != b["version"]
            ):
                return "💬 No hay un cambio pendiente para confirmar. Contame qué querés modificar."
            if propuesta.get("operativa"):
                return await self._operar_datos(b, {"id": "confirmacion"}, propuesta)
            if propuesta.get("operacion") != self._foto_operacion(pedido):
                self._limpiar_solicitud(b)
                return CONVERSACION_CAMBIADA
            accion = propuesta["accion"]
            nombre = accion["accion"]
        else:
            propuesta = None
        if nombre not in {"quitar_ingrediente", "cantidad"}:
            return resumen(pedido) + "\n\n" + estado_pedido(pedido)
        args = accion.get("argumentos", {})
        if set(args) - {"ingrediente", "item_indice", "cantidad"}:
            return "💬 No puedo hacer ese cambio automáticamente. Pedí hablar con un empleado."
        candidatos = pedido["items"]
        indice = args.get("item_indice")
        if indice is not None:
            if (
                isinstance(indice, bool)
                or not isinstance(indice, int)
                or not 1 <= indice <= len(candidatos)
            ):
                return "💬 Decime qué producto querés modificar para no cambiar otro por error."
            candidatos = [candidatos[indice - 1]]
        elif nombre == "quitar_ingrediente":
            ingrediente = str(args.get("ingrediente", "")).casefold()
            candidatos = [
                i
                for i in candidatos
                if ingrediente
                in {r["nombre"].casefold() for r in await self._ingredientes_item(i)}
            ]
        if len(candidatos) != 1:
            b["propuesta"] = {"tipo": "ACLARACION", "version": b["version"], "accion": accion}
            listado = "; ".join(
                f"{n}: {i['nombre_producto']}" for n, i in enumerate(pedido["items"], 1)
            )
            return (
                f"🍔 ¿Cuál producto querés modificar?\n{listado}\n"
                "Respondé *producto N*."
            )
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
                return "💬 ¿Cuántas unidades querés? Elegí un número entero entre 1 y 50."
        else:
            ingrediente = str(args.get("ingrediente", "")).casefold()
            receta = {
                r["nombre"].casefold() for r in await self._ingredientes_item(item)
            }
            if ingrediente not in QUITABLES & receta:
                return (
                    "💬 Ese ingrediente no se puede quitar de este producto. "
                    "Si necesitás otro cambio, un empleado te puede ayudar."
                )
            if f"sin {ingrediente}" in notas.casefold():
                return "✅ Tu producto ya está guardado sin ese ingrediente.\n\n" + resumen(pedido)
            notas = re.sub(
                r"\bcon\s+" + re.escape(ingrediente) + r"\b", "", notas, flags=re.I
            ).strip(" ,;")
            if f"sin {ingrediente}" not in notas.casefold():
                notas = ", ".join(filter(None, [notas, f"Sin {ingrediente.capitalize()}"]))
        total = pedido["total"] + (cantidad - item["cantidad"]) * (
            item["precio_unitario"] + item["costo_opciones"]
        )
        if total < 0:
            return "💬 Para ese cambio necesitamos que un empleado revise los descuentos."
        anterior = {
            "item_id": item["id"],
            "cantidad": item["cantidad"],
            "aclaraciones": item["aclaraciones"],
            "total": str(pedido["total"]),
            "pedido_version": pedido["version"],
        }
        posterior = {"cantidad": cantidad, "aclaraciones": notas, "total": str(total)}
        if pedido["estado"] in {"ENTREGADO", "CANCELADO"}:
            return "💬 Este pedido ya está cerrado. Escribinos y un empleado te ayuda."
        requiere_personal = pedido.get("preparacion_en") is not None or (
            pedido["estado"] not in {"PENDIENTE", "CONFIRMADO"}
        ) or (total != pedido["total"] and pedido["pagado"] > 0)
        if (
            total != pedido["total"]
            and pedido["pagado"] == 0
            and propuesta is None
            and empleado_id is None
            and not requiere_personal
        ):
            b["propuesta"] = {
                "tipo": "TOTAL",
                "version": b["version"],
                "accion": accion,
                "total": str(total),
                "total_anterior": str(pedido["total"]),
                "operacion": self._foto_operacion(pedido),
            }
            return (
                f"💰 El nuevo total sería *{dinero(total)}*.\n"
                "Respondé *confirmar* para aplicar el cambio."
            )
        if propuesta and (
            Decimal(propuesta["total"]) != total
            or Decimal(propuesta["total_anterior"]) != pedido["total"]
        ):
            b["propuesta"] = None
            return "💬 El total cambió mientras conversábamos. ¿Me repetís el cambio?"
        if requiere_personal and empleado_id is None:
            await self.repo.historial(b, accion, anterior, posterior, "PENDIENTE_EMPLEADO")
            b["estado"] = "HUMANO"
            b["propuesta"] = None
            return (
                "👨‍🍳 El cambio requiere aprobación de un empleado porque tu pedido "
                "ya está en marcha o tiene pagos. Le pasamos tu solicitud; "
                "el pedido sigue sin cambios por ahora."
            )
        if nombre == "cantidad" and cantidad > item["cantidad"]:
            # La disponibilidad de venta solo limita lo que requiere insumos adicionales;
            # retirar ingredientes o reducir unidades devuelve stock ya consumido.
            productos = await self.pedidos.repo.productos([item["producto_id"]])
            if not productos or not productos[0]["disponible"]:
                return (
                    "💬 El producto no tiene stock para agregar más unidades. "
                    "Tu pedido sigue sin cambios; un empleado te puede ayudar."
                )
        acumulado = sum(
            i["cantidad"]
            for i in pedido["items"]
            if i["producto_id"] == item["producto_id"]
            and i["nombre_producto"] == item["nombre_producto"]
        )
        if acumulado + cantidad - item["cantidad"] > 50:
            return "💬 Podemos tomar hasta 50 unidades de una misma variante por pedido."
        if (
            nombre == "quitar_ingrediente"
            and pedido["stock_consumido"]
            and pedido.get("preparacion_en") is None
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
        await self.repo.aplicar_item(pedido, item, cantidad, notas or None, empleado_id)
        if (
            b["metodo_pago"] == "TRANSFERENCIA"
            and total != pedido["total"]
            and total > pedido["pagado"]
        ):
            b["estado_pago"] = "PENDIENTE"
        b["version"] += 1
        b["propuesta"] = None
        await self.repo.historial(b, accion, anterior, posterior, "APLICADO", empleado_id)
        return "✅ Cambio guardado. Ya le pasamos la actualización a cocina.\n\n" + resumen(
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
            if cambio["anterior"].get("pedido_version") != pedido["version"]:
                raise ReglaDeNegocio("La versión del pedido cambió: solicitá una nueva revisión")
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
            version_anterior = b["version"]
            respuesta = await self._operar(b, "", cambio["accion"], empleado_id)
            if b["version"] != version_anterior + 1:
                raise ReglaDeNegocio(respuesta)
            b["estado"] = "CREADO"
            if nuevo_total > pedido["pagado"]:
                if b["metodo_pago"] == "TRANSFERENCIA":
                    b["estado_pago"] = "PENDIENTE"
                respuesta += f"\n💰 Saldo pendiente: *{dinero(nuevo_total-pedido['pagado'])}*."
        else:
            respuesta = "💬 No pudimos aplicar el cambio de tu pedido. " + motivo
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
