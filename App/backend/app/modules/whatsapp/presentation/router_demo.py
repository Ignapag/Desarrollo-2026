"""Transporte web privado para una demo explícita; reutiliza inbox y núcleo del bot."""

import hashlib
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.conninfo import conninfo_to_dict
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.dependencias import UoW
from app.errores import DatosInvalidos, NoAutenticado, SinPermiso
from app.modules.whatsapp.domain.mensajes import es_inicio_web, tiene_token_referencia
from app.modules.whatsapp.infrastructure.canal_demo import COOKIE_DEMO, MAX_ARCHIVO, CanalDemoSQL
from app.modules.whatsapp.presentation.dependencias import construir_servicio
from app.modules.whatsapp.presentation.esquemas import BorradorEntrada

router = APIRouter(prefix="/api/chat-demo", tags=["Chat de demostración"])


def habilitado():
    """Indica si el chat de demostración está habilitado: por perfil público autorizado o en
    desarrollo simulado con base de datos estrictamente local.
    """
    if settings.chat_demo_habilitado and settings.chat_demo_bd_compartida_autorizada:
        # Publicación intencional: el canal se enruta por sesión, nunca hacia Meta.
        return True
    if (
        not settings.chat_demo_habilitado
        or settings.es_produccion
        or settings.whatsapp_modo != "simulado"
    ):
        return False
    # La demo nunca usa silenciosamente App/.env ni una conexión indirecta remota.
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        opciones = conninfo_to_dict(settings.database_url)
    except Exception:
        return False
    locales = {"localhost", "127.0.0.1", "::1"}
    return (
        opciones.get("host") in locales
        and not opciones.get("service")
        and not os.environ.get("PGSERVICE")
        and all(
            not valor or valor in locales
            for valor in (
                opciones.get("hostaddr"),
                os.environ.get("PGHOST"),
                os.environ.get("PGHOSTADDR"),
            )
        )
    )


def validar_canal(request: Request):
    """Dependencia que exige el canal habilitado y, en POST, la cabecera propia y un origen
    permitido.
    """
    if not habilitado():
        raise SinPermiso("El chat de demostración no está habilitado en este entorno")
    if request.method == "POST":
        propio = str(request.base_url).rstrip("/")
        origen = request.headers.get("origin")
        if request.headers.get("x-chat-demo") != "1" or (
            origen and origen not in {propio, *settings.origenes_permitidos}
        ):
            raise SinPermiso("Origen de la solicitud no permitido")


CanalHabilitado = Annotated[None, Depends(validar_canal)]


def validar_cookie(request: Request, canal: CanalHabilitado):
    """Dependencia que devuelve el token de la cookie de demostración o rechaza la solicitud."""
    token = request.cookies.get(COOKIE_DEMO)
    if not token or len(token) > 100:
        raise NoAutenticado("Abrí una sesión de demostración para continuar")
    return token


TokenDemo = Annotated[str, Depends(validar_cookie)]


class InicioDemo(BaseModel):
    """Inicio de la demostración: carrito web con su UUID de intento."""

    model_config = ConfigDict(extra="forbid")
    solicitud_id: UUID
    borrador: BorradorEntrada


class MensajeDemo(BaseModel):
    """Mensaje de texto del chat de demostración con su UUID de intento."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    solicitud_id: UUID
    texto: str = Field(min_length=1, max_length=2000)


def proveedor():
    """Modo de interpretación vigente para la demostración."""
    return {
        "interpretador": settings.chat_demo_gemini_modo or settings.gemini_modo,
        "gemini_configurado": bool(settings.gemini_api_key),
    }


@router.get("/config")
async def configuracion(response: Response):
    """Indica al navegador si la demostración está habilitada y con qué intérprete."""
    response.headers["Cache-Control"] = "no-store"
    return {"habilitado": habilitado(), **proveedor()}


@router.post("/sesion")
async def abrir_sesion(request: Request, response: Response, canal: CanalHabilitado, uow: UoW):
    """Reutiliza la sesión de la cookie o crea una nueva, y fija la cookie httponly."""
    repo = CanalDemoSQL(uow)
    token = request.cookies.get(COOKIE_DEMO)
    try:
        await repo.sesion(token)
    except NoAutenticado:
        token = await repo.crear_sesion()
    response.set_cookie(
        COOKIE_DEMO,
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=7 * 24 * 3600,
        path="/api/chat-demo",
    )
    response.headers["Cache-Control"] = "no-store"
    return {}


@router.get("/conversacion")
async def conversacion(response: Response, token: TokenDemo, uow: UoW):
    """Historial del chat de demostración de la sesión."""
    repo = CanalDemoSQL(uow)
    sesion = await repo.sesion(token)
    response.headers["Cache-Control"] = "private, no-store"
    return {**await repo.conversacion(sesion), **proveedor()}


@router.post("/borradores", status_code=202)
async def iniciar(datos: InicioDemo, token: TokenDemo, uow: UoW):
    """Crea el borrador desde el carrito y lo envía como primer mensaje del chat; un reintento con
    el mismo UUID devuelve el resultado anterior.
    """
    repo = CanalDemoSQL(uow)
    sesion = await repo.sesion(token, bloquear=True)
    contenido = {"tipo": "borrador", **datos.borrador.model_dump()}
    anterior = await repo.intento(sesion, datos.solicitud_id, contenido)
    if anterior:
        return anterior
    servicio = construir_servicio(uow)
    # Referencia de transporte interna aleatoria: no se acepta ninguna del navegador.
    borrador = await servicio.crear_borrador(
        None, {**datos.borrador.model_dump(), "contacto": None}
    )
    await repo.vincular_borrador(
        sesion, borrador["referencia"], datos.borrador.model_dump()["contacto"]
    )
    identificador = repo.identificador(sesion, datos.solicitud_id)
    await servicio.recibir(identificador, sesion["telefono"], borrador["mensaje"])
    return await repo.registrar(sesion, datos.solicitud_id, contenido, identificador)


@router.post("/mensajes", status_code=202)
async def recibir(datos: MensajeDemo, token: TokenDemo, uow: UoW):
    """Registra un mensaje de texto del chat de demostración; no admite referencias ni resúmenes de
    carrito.
    """
    if tiene_token_referencia(datos.texto) or es_inicio_web(datos.texto):
        raise DatosInvalidos("Para enviar un carrito usá Continuar en el chat desde el menú")
    repo = CanalDemoSQL(uow)
    sesion = await repo.sesion(token, bloquear=True)
    contenido = {"tipo": "texto", "texto": datos.texto}
    anterior = await repo.intento(sesion, datos.solicitud_id, contenido)
    if anterior:
        return anterior
    identificador = repo.identificador(sesion, datos.solicitud_id)
    await construir_servicio(uow).recibir(identificador, sesion["telefono"], datos.texto)
    return await repo.registrar(sesion, datos.solicitud_id, contenido, identificador)


def validar_archivo(contenido, mime):
    """Verifica que el archivo sea un PDF, PNG o JPEG por su firma de bytes."""
    firmas = {
        "application/pdf": b"%PDF-",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
    }
    if mime not in firmas or not contenido.startswith(firmas[mime]):
        raise DatosInvalidos("Adjuntá un PDF, PNG o JPEG válido de hasta 2 MiB")


@router.post("/comprobantes", status_code=202)
async def adjuntar(request: Request, token: TokenDemo, uow: UoW):
    """Recibe un comprobante adjunto (hasta 2 MiB), lo guarda y lo registra como mensaje con
    archivo.
    """
    try:
        solicitud_id = UUID(request.headers.get("x-solicitud-id", ""))
    except ValueError as exc:
        raise DatosInvalidos("El comprobante necesita un identificador de intento UUID") from exc
    contenido = bytearray()
    async for parte in request.stream():
        contenido.extend(parte)
        if len(contenido) > MAX_ARCHIVO:
            raise HTTPException(413, "El comprobante supera 2 MiB")
    contenido = bytes(contenido)
    mime = request.headers.get("content-type", "").split(";", 1)[0]
    validar_archivo(contenido, mime)
    repo = CanalDemoSQL(uow)
    sesion = await repo.sesion(token, bloquear=True)
    firma = {"tipo": "archivo", "mime": mime, "sha256": hashlib.sha256(contenido).hexdigest()}
    anterior = await repo.intento(sesion, solicitud_id, firma)
    if anterior:
        return anterior
    identificador = repo.identificador(sesion, solicitud_id)
    media_id = "demo:" + identificador
    await construir_servicio(uow).recibir(identificador, sesion["telefono"], "", media_id)
    await repo.guardar_archivo(sesion, identificador, media_id, contenido, mime)
    return await repo.registrar(sesion, solicitud_id, firma, identificador)


def respuesta_archivo(contenido, mime):
    """Respuesta HTTP de descarga del comprobante, sin caché ni detección de tipo."""
    return Response(
        contenido,
        media_type=mime,
        headers={
            "Content-Disposition": 'attachment; filename="comprobante-demo"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/comprobantes/{entrada_id}/archivo")
async def descargar(entrada_id: str, token: TokenDemo, uow: UoW):
    """Descarga un comprobante propio de la sesión de demostración."""
    repo = CanalDemoSQL(uow)
    sesion = await repo.sesion(token)
    archivo = await repo.archivo(entrada_id, sesion)
    return respuesta_archivo(archivo["contenido"], archivo["mime"])
