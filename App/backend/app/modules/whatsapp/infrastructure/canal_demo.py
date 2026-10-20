"""Identidad y almacenamiento del adaptador web; no ejecuta reglas de pedidos."""

import hashlib
import json
import secrets

from psycopg.types.json import Jsonb

from app.errores import NoAutenticado, NoEncontrado, ReglaDeNegocio
from app.modules.whatsapp.domain.mensajes import (
    hash_referencia,
    ocultar_referencias,
    referencia_en,
)

COOKIE_DEMO = "monu_chat_demo"
MAX_ARCHIVO = 2 * 1024 * 1024


def huella(datos):
    return hashlib.sha256(
        json.dumps(datos, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class CanalDemoSQL:
    def __init__(self, uow):
        self.uow = uow

    async def sesion(self, token, bloquear=False):
        if not token or len(token) > 100:
            raise NoAutenticado("Abrí una sesión de demostración para continuar")
        token_hash = hash_referencia(token)
        if bloquear:
            await self.uow.valor(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("demo:" + token_hash,),
            )
        sesion = await self.uow.uno(
            "SELECT * FROM chat_demo_sesion WHERE token_hash=%s AND expira_en>now()",
            (token_hash,),
        )
        if not sesion:
            raise NoAutenticado("La sesión de demostración venció. Abrí una nueva sesión")
        return sesion

    async def crear_sesion(self):
        await self._presupuesto()
        cantidad = await self.uow.valor(
            "SELECT count(*) FROM chat_demo_sesion WHERE creado_en>now()-interval '1 day'"
        )
        if cantidad >= 100:
            raise ReglaDeNegocio("Se alcanzó el límite diario de sesiones de demostración")
        token = secrets.token_urlsafe(32)
        telefono = "000" + str(secrets.randbelow(10**12)).zfill(12)
        cliente_id = await self.uow.valor(
            "INSERT INTO cliente(nombre,telefono_whatsapp) VALUES ('Cliente de demostración',%s) "
            "RETURNING id",
            (telefono,),
        )
        await self.uow.ejecutar(
            "INSERT INTO chat_demo_sesion(token_hash,telefono,cliente_id) VALUES (%s,%s,%s)",
            (hash_referencia(token), telefono, cliente_id),
        )
        return token

    async def _presupuesto(self):
        # Serializa el presupuesto global, sin llamadas a proveedores en este alcance.
        await self.uow.valor("SELECT pg_advisory_xact_lock(hashtext('chat-demo-presupuesto'))")

    async def intento(self, sesion, solicitud_id, contenido):
        """Replay antes de límites; cambiar el contenido de un UUID produce conflicto."""
        firma = huella(contenido)
        anterior = await self.uow.uno(
            """SELECT o.huella,e.id,e.estado FROM chat_demo_operacion o
            JOIN whatsapp_entrada e ON e.id=o.entrada_id
            WHERE o.sesion_hash=%s AND o.solicitud_id=%s""",
            (sesion["token_hash"], solicitud_id),
        )
        if anterior:
            if anterior["huella"] != firma:
                raise ReglaDeNegocio("Ese intento ya se usó con otro contenido")
            return {"id": anterior["id"], "estado": anterior["estado"]}
        await self._presupuesto()
        cuenta = await self.uow.uno(
            """SELECT count(*) total,
            count(*) FILTER (WHERE sesion_hash=%s) propia
            FROM chat_demo_operacion WHERE creado_en>now()-interval '1 day'""",
            (sesion["token_hash"],),
        )
        if cuenta["total"] >= 300 or cuenta["propia"] >= 80:
            raise ReglaDeNegocio("Se alcanzó el límite diario de mensajes de la demostración")
        if await self.uow.valor(
            "SELECT EXISTS(SELECT 1 FROM whatsapp_entrada "
            "WHERE telefono=%s AND estado='PENDIENTE')",
            (sesion["telefono"],),
        ):
            raise ReglaDeNegocio("Esperá a que termine el mensaje anterior antes de continuar")
        return None

    @staticmethod
    def identificador(sesion, solicitud_id):
        return "web:" + sesion["token_hash"] + ":" + str(solicitud_id)

    async def registrar(self, sesion, solicitud_id, contenido, entrada_id):
        await self.uow.ejecutar(
            """INSERT INTO chat_demo_operacion(sesion_hash,solicitud_id,huella,entrada_id)
            VALUES (%s,%s,%s,%s)""",
            (sesion["token_hash"], solicitud_id, huella(contenido), entrada_id),
        )
        return {"id": entrada_id, "estado": "PENDIENTE"}

    async def vincular_borrador(self, sesion, referencia, contacto):
        # El teléfono declarado es comercial. Jamás fija whatsapp_verificado.
        await self.uow.ejecutar(
            """UPDATE whatsapp_borrador SET telefono=%s,cliente_id=%s,contacto=%s
            WHERE referencia_hash=%s AND telefono IS NULL""",
            (
                sesion["telefono"],
                sesion["cliente_id"],
                Jsonb(contacto or {}),
                hash_referencia(referencia[3:]),
            ),
        )
        if contacto:
            await self.uow.ejecutar(
                "UPDATE cliente SET nombre=%s,telefono_contacto=%s WHERE id=%s",
                (
                    contacto["nombre"] + " " + contacto["apellido"],
                    contacto["telefono"],
                    sesion["cliente_id"],
                ),
            )

    async def guardar_archivo(self, sesion, entrada_id, media_id, contenido, mime):
        await self.uow.ejecutar(
            """INSERT INTO chat_demo_archivo(media_id,sesion_hash,entrada_id,contenido,mime)
            VALUES (%s,%s,%s,%s,%s)""",
            (media_id, sesion["token_hash"], entrada_id, contenido, mime),
        )

    async def archivo(self, entrada_id, sesion):
        archivo = await self.uow.uno(
            "SELECT contenido,mime FROM chat_demo_archivo WHERE entrada_id=%s AND sesion_hash=%s",
            (entrada_id, sesion["token_hash"]),
        )
        if not archivo:
            raise NoEncontrado("El archivo no existe")
        return archivo

    async def conversacion(self, sesion):
        telefono = sesion["telefono"]
        mensajes = await self.uow.todos(
            """SELECT * FROM (
                SELECT id,'cliente' direccion,texto,estado,creado_en,
                    media_id IS NOT NULL tiene_archivo,orden_recibido orden
                    FROM whatsapp_entrada WHERE telefono=%s
                UNION ALL
                SELECT 'salida:'||id,'bot',texto,estado,creado_en,false,id
                    FROM whatsapp_salida WHERE telefono=%s
            ) m ORDER BY creado_en DESC,(direccion='bot') DESC,orden DESC LIMIT 200""",
            (telefono, telefono),
        )
        borradores = await self.uow.todos(
            """SELECT b.referencia_hash,b.pedido_id,b.estado,b.expira_en,
                (SELECT jsonb_agg(i || jsonb_build_object('nombre',pr.nombre))
                 FROM jsonb_array_elements(b.items) i
                 JOIN producto pr ON pr.id=(i->>'producto_id')::bigint) items,p.numero,
                p.estado estado_pedido,p.total FROM whatsapp_borrador b
                LEFT JOIN pedido p ON p.id=b.pedido_id WHERE b.telefono=%s
                ORDER BY b.creado_en DESC LIMIT 20""",
            (telefono,),
        )
        por_referencia = {b.pop("referencia_hash"): b for b in borradores}
        for mensaje in mensajes:
            mensaje.pop("orden")
            referencia = referencia_en(mensaje["texto"])
            borrador = por_referencia.get(hash_referencia(referencia)) if referencia else None
            if borrador and mensaje["direccion"] == "cliente":
                lineas = ["Quiero continuar el pedido del carrito:"]
                for item in borrador["items"]:
                    variante = f" ({item['variante']})" if item.get("variante") else ""
                    notas = f" · {item['aclaraciones']}" if item.get("aclaraciones") else ""
                    lineas.append(f"{item['cantidad']} × {item['nombre']}{variante}{notas}")
                mensaje["texto"] = "\n".join(lineas)
            else:
                mensaje["texto"] = ocultar_referencias(mensaje["texto"])
        return {"mensajes": list(reversed(mensajes)), "borradores": borradores}
