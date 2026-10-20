"""Worker invocable por CLI: etapas con transacciones independientes y acotadas."""

import asyncio
import logging

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
CONVERSACIONES_SIMULTANEAS = 3


async def _interpretar(preparado):
    if len(preparado["texto"]) > LIMITE_INTERPRETACION:
        # Se deriva el mensaje completo; nunca se interpreta un prefijo.
        return {"accion": "humano", "argumentos": {}, "motivo": "MENSAJE_LARGO"}
    modo_demo = settings.chat_demo_gemini_modo if preparado.get("canal_demo") else None
    try:
        proveedor = interpretador(modo_demo) if modo_demo else interpretador()
        return await proveedor.interpretar(preparado["texto"], preparado["contexto"])
    except Exception as error:
        # Frontera externa: no dejar el inbox pendiente por una respuesta inesperada.
        # Cancelación del worker sigue propagándose (BaseException).
        logging.getLogger("monuburger.whatsapp.proveedor").warning(
            "whatsapp_interpretacion_no_controlada clase=%s", type(error).__name__,
        )
        return {"accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR"}


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
        except Exception as error:
            # La conexión del intento ya salió con rollback. Si la base responde,
            # cerrar el inbox con una salida controlada en una transacción nueva.
            logging.getLogger("monuburger.whatsapp.procesamiento").error(
                "whatsapp_operacion_no_controlada clase=%s", type(error).__name__,
            )
            await _finalizar_fallido(identificador)
            return


async def _finalizar_fallido(identificador):
    # La transacción del intento fallido ya revirtió todos sus efectos.
    async with conexion() as conn:
        servicio = construir_servicio(UnidadDeTrabajo(conn))
        entrada = await servicio.repo.entrada(identificador, bloquear=True)
        if entrada and entrada["estado"] != "PROCESADO":
            b, _ = await servicio._conversacion(entrada, bloquear=True)
            if b:
                await servicio._derivar(b, entrada, {"accion": "humano", "motivo": "PROVEEDOR"})
            else:
                await servicio.repo.derivar_general(identificador, "PROVEEDOR")
            await servicio.repo.finalizar(
                entrada,
                b,
                "💬 No pude aplicar el cambio. Tu pedido sigue sin cambios. "
                "Tu solicitud quedó para revisión. Escribí *ayuda* para continuar "
                "con opciones guiadas o *empleado* para atención personal.",
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


async def _procesar_conversacion(entradas, cupos):
    async with cupos:
        for entrada in entradas:
            try:
                await procesar_entrada(entrada["id"])
            except Exception as error:
                # Un fallo de conexión/preparación no debe bloquear otros clientes.
                # El siguiente mensaje de ESTE cliente espera al próximo ciclo,
                # para no adelantarlo al que sigue pendiente en el inbox.
                logging.getLogger("monuburger.whatsapp.procesamiento").warning(
                    "whatsapp_conversacion_pendiente clase=%s", type(error).__name__,
                )
                break


async def procesar_lote(limite=20, *, solo_demo=False):
    async with conexion() as conn:
        pendientes = await ColaWhatsAppSQL(UnidadDeTrabajo(conn)).pendientes(
            limite, solo_demo=solo_demo,
        )
    conversaciones = {}
    for entrada in pendientes:
        conversaciones.setdefault(entrada["telefono"], []).append(entrada)
    # Cada teléfono conserva el orden del inbox, incluso durante la llamada a IA.
    # Los cupos limitan tanto proveedores como transacciones, nunca sus alcances.
    cupos = asyncio.Semaphore(CONVERSACIONES_SIMULTANEAS)
    await asyncio.gather(*(
        _procesar_conversacion(entradas, cupos) for entradas in conversaciones.values()
    ))
    for _ in range(limite):
        if not await enviar_uno(solo_demo=solo_demo):
            break
    return {"entradas": len(pendientes)}
