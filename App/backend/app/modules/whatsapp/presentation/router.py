"""Webhooks públicos con firma propia y operaciones internas con roles."""

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, conexion
from app.core.dependencias import UoW
from app.errores import DatosInvalidos, NoEncontrado, SinPermiso
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import SoloCliente, requiere_rol
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.infrastructure.proveedores import validar_firma
from app.modules.whatsapp.presentation.dependencias import (
    ServicioBotDep,
    construir_servicio,
    transporte,
)
from app.modules.whatsapp.presentation.esquemas import (
    BorradorEntrada,
    MensajeSimulado,
    ResolucionAtencionEntrada,
    RespuestaAtencionEntrada,
    RevisionEntrada,
)

router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])
Empleado = Annotated[
    ClaimsSesion, Depends(requiere_rol(Rol.EMPLEADO, Rol.ADMINISTRADOR, Rol.DUENIO))
]


@router.post("/borradores", status_code=201)
async def crear_borrador(datos: BorradorEntrada, sesion: SoloCliente, servicio: ServicioBotDep):
    return await servicio.crear_borrador(sesion.usuario_id, datos.model_dump())


@router.post("/simular", status_code=202)
async def simular(datos: MensajeSimulado, personal: Empleado, servicio: ServicioBotDep):
    if settings.es_produccion or settings.whatsapp_modo != "simulado":
        raise SinPermiso("La simulación solo está habilitada en desarrollo simulado")
    await servicio.recibir(datos.id, datos.telefono, datos.texto, datos.media_id)
    return {"estado": "PENDIENTE", "id": datos.id}


@router.get("/bandeja")
async def bandeja(personal: Empleado, uow: UoW):
    return await ColaWhatsAppSQL(uow).bandeja()


@router.post("/comprobantes/{comprobante_id}/revision")
async def revisar(
    comprobante_id: int, datos: RevisionEntrada, personal: Empleado, servicio: ServicioBotDep
):
    return await servicio.revisar_comprobante(
        comprobante_id,
        datos.aprobar,
        personal.usuario_id,
        datos.motivo,
        total_verificado=datos.total_verificado,
    )


@router.get("/comprobantes/{comprobante_id}/archivo")
async def archivo(comprobante_id: int, personal: Empleado):
    async with conexion() as conn:
        fila = await UnidadDeTrabajo(conn).uno(
            "SELECT media_id FROM whatsapp_comprobante WHERE id=%s", (comprobante_id,)
        )
    if not fila:
        raise NoEncontrado("El comprobante no existe")
    if settings.whatsapp_modo != "real":
        raise DatosInvalidos("El adjunto simulado no tiene archivo real")
    contenido, mime = await transporte().bajar_comprobante(fila["media_id"])
    return Response(
        contenido,
        media_type=mime,
        headers={
            "Content-Disposition": 'attachment; filename="comprobante"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/cambios/{cambio_id}/revision")
async def revisar_cambio(
    cambio_id: int, datos: RevisionEntrada, personal: Empleado, servicio: ServicioBotDep
):
    return await servicio.revisar_cambio(
        cambio_id,
        datos.aprobar,
        personal.usuario_id,
        datos.motivo,
        total_verificado=datos.total_verificado,
        resolucion_financiera=datos.resolucion_financiera,
    )


@router.post("/atenciones/{atencion_id}/respuesta", status_code=202)
async def responder_atencion(
    atencion_id: int,
    datos: RespuestaAtencionEntrada,
    personal: Empleado,
    servicio: ServicioBotDep,
):
    # 202: queda en la outbox; el estado de envío real se consulta en la bandeja.
    return await servicio.responder_atencion(
        atencion_id, personal.usuario_id, datos.texto, str(datos.solicitud_id)
    )


@router.post("/atenciones/{atencion_id}/resolucion")
async def resolver_atencion(
    atencion_id: int,
    datos: ResolucionAtencionEntrada,
    personal: Empleado,
    servicio: ServicioBotDep,
):
    return await servicio.resolver_atencion(atencion_id, personal.usuario_id, datos.resolucion)


@router.get("/webhook")
async def verificar(request: Request):
    query = request.query_params
    recibido = query.get("hub.verify_token", "")
    if (
        settings.whatsapp_modo != "real"
        or not settings.whatsapp_verify_token
        or not hmac.compare_digest(recibido.encode(), settings.whatsapp_verify_token.encode())
        or query.get("hub.mode") != "subscribe"
    ):
        raise HTTPException(403, "Verificación rechazada")
    return Response(query.get("hub.challenge", ""), media_type="text/plain")


@router.post("/webhook")
async def webhook(request: Request):
    if settings.whatsapp_modo != "real":
        raise HTTPException(403, "El webhook real no está habilitado")
    cuerpo = bytearray()
    async for parte in request.stream():
        cuerpo.extend(parte)
        if len(cuerpo) > 262144:
            raise HTTPException(413, "Webhook demasiado grande")
    if not validar_firma(
        bytes(cuerpo), request.headers.get("x-hub-signature-256"), settings.whatsapp_app_secret
    ):
        raise HTTPException(403, "Firma inválida")
    try:
        payload = json.loads(cuerpo)
        if payload.get("object") != "whatsapp_business_account":
            raise ValueError
        eventos = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                valor = change["value"]
                if (
                    valor.get("metadata", {}).get("phone_number_id")
                    != settings.whatsapp_phone_number_id
                ):
                    continue
                eventos.append(valor)
        async with conexion() as conn:
            uow = UnidadDeTrabajo(conn)
            servicio = construir_servicio(uow)
            for valor in eventos:
                for m in valor.get("messages", []):
                    tipo = m.get("type")
                    media = m.get(tipo, {}).get("id") if tipo in {"image", "document"} else None
                    if tipo == "text":
                        texto = m.get("text", {}).get("body", "")
                    elif media:
                        # El pie del adjunto puede traer la referencia MB- del pedido.
                        texto = m[tipo].get("caption", "")
                    else:
                        texto = "atención humana"
                    await servicio.recibir(m["id"], m["from"], texto, media)
                for estado in valor.get("statuses", []):
                    await ColaWhatsAppSQL(uow).estado_proveedor(
                        estado["id"], estado.get("recipient_id", ""), estado["status"]
                    )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(400, "Formato de webhook inválido") from exc
    return {"estado": "RECIBIDO"}
