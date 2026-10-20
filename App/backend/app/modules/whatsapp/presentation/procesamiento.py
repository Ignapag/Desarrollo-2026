"""Worker invocable por CLI: etapas con transacciones independientes y acotadas."""

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, conexion
from app.errores import ErrorDominio, ReglaDeNegocio
from app.modules.whatsapp.application.servicio_bot import InterpretacionDesactualizada
from app.modules.whatsapp.domain.mensajes import LIMITE_INTERPRETACION
from app.modules.whatsapp.infrastructure.cola import ColaWhatsAppSQL
from app.modules.whatsapp.infrastructure.proveedores import ErrorEnvioIncierto
from app.modules.whatsapp.presentation.dependencias import (
    construir_servicio,
    interpretador,
    transporte,
)

CONSULTA = {"accion": "consulta", "argumentos": {}}
# Una reinterpretación si el mismo pedido cambió durante la llamada al proveedor.
INTENTOS_INTERPRETACION = 2


async def _interpretar(preparado):
    if len(preparado["texto"]) > LIMITE_INTERPRETACION:
        # Se deriva el mensaje completo; nunca se interpreta un prefijo.
        return {"accion": "humano", "argumentos": {}, "motivo": "MENSAJE_LARGO"}
    modo_demo = settings.chat_demo_gemini_modo if preparado.get("canal_demo") else None
    proveedor = interpretador(modo_demo) if modo_demo else interpretador()
    return await proveedor.interpretar(preparado["texto"], preparado["contexto"])


async def procesar_entrada(identificador):
    for intento in range(INTENTOS_INTERPRETACION):
        async with conexion() as conn:
            uow = UnidadDeTrabajo(conn)
            preparado = await construir_servicio(uow).preparar(identificador)
            if preparado and preparado["interpretar"] and settings.chat_demo_gemini_modo:
                preparado["canal_demo"] = await uow.valor(
                    """SELECT EXISTS(SELECT 1 FROM chat_demo_sesion d
                    JOIN whatsapp_entrada e ON e.telefono=d.telefono WHERE e.id=%s)""",
                    (identificador,),
                )
        if preparado is None:
            return
        # El foco también puede cambiar entre etapas de un adjunto o comando guiado.
        # Conservar siempre su vínculo; solo el texto que lo necesita consume IA.
        vinculo = preparado["vinculo"]
        accion = await _interpretar(preparado) if preparado["interpretar"] else CONSULTA
        try:
            async with conexion() as conn:
                await construir_servicio(UnidadDeTrabajo(conn)).procesar(
                    identificador,
                    accion,
                    vinculo,
                    reintentar=intento + 1 < INTENTOS_INTERPRETACION,
                )
            return
        except InterpretacionDesactualizada:
            continue
        except ErrorDominio:
            await _finalizar_fallido(identificador)
            return


async def _finalizar_fallido(identificador):
    # La transacción del intento fallido ya revirtió todos sus efectos.
    async with conexion() as conn:
        servicio = construir_servicio(UnidadDeTrabajo(conn))
        entrada = await servicio.repo.entrada(identificador, bloquear=True)
        if entrada and entrada["estado"] != "PROCESADO":
            await servicio.repo.finalizar(
                entrada,
                None,
                "💬 No pude aplicar el cambio. Tu pedido sigue sin cambios. "
                "Pedí hablar con un empleado y te ayudamos por acá.",
            )


async def enviar_uno(*, solo_demo=False):
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        cola = ColaWhatsAppSQL(uow)
        mensaje = await cola.reclamar(solo_demo=True) if solo_demo else await cola.reclamar()
        if not mensaje:
            return False
        # La identidad del canal perdura aunque venza o se deshabilite la demo.
        if await uow.valor(
            "SELECT EXISTS (SELECT 1 FROM chat_demo_sesion WHERE telefono=%s)",
            (mensaje["telefono"],),
        ):
            await cola.resultado(mensaje["id"], "SIMULADO")
            return True
        if settings.whatsapp_modo == "real" and not await cola.dentro_ventana(mensaje["telefono"]):
            await cola.resultado(mensaje["id"], "FALLIDO")
            # Fuera de ventana requiere plantilla; queda retenido para personal.
            await UnidadDeTrabajo(conn).ejecutar(
                "UPDATE whatsapp_salida SET intentos=3 WHERE id=%s", (mensaje["id"],)
            )
            return True
    estado, proveedor_id = "FALLIDO", None
    try:
        proveedor_id = await transporte().enviar(mensaje["telefono"], mensaje["texto"])
        estado = "ACEPTADO" if settings.whatsapp_modo == "real" else "SIMULADO"
    except ErrorEnvioIncierto:
        estado = "INCIERTO"
    except ReglaDeNegocio:
        estado = "FALLIDO"
    async with conexion() as conn:
        await ColaWhatsAppSQL(UnidadDeTrabajo(conn)).resultado(mensaje["id"], estado, proveedor_id)
    return True


async def procesar_lote(limite=20, *, solo_demo=False):
    async with conexion() as conn:
        pendientes = await ColaWhatsAppSQL(UnidadDeTrabajo(conn)).pendientes(
            limite, solo_demo=solo_demo,
        )
    for entrada in pendientes:
        await procesar_entrada(entrada["id"])
    for _ in range(limite):
        if not await enviar_uno(solo_demo=solo_demo):
            break
    return {"entradas": len(pendientes)}
