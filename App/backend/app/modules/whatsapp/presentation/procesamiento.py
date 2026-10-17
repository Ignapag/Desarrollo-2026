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
    return await interpretador().interpretar(preparado["texto"], preparado["contexto"])


async def procesar_entrada(identificador):
    for intento in range(INTENTOS_INTERPRETACION):
        async with conexion() as conn:
            preparado = await construir_servicio(UnidadDeTrabajo(conn)).preparar(identificador)
        if preparado is None:
            return
        # Adjuntos, saludo de la web y comandos guiados no consumen IA ni requieren vínculo.
        vinculo = preparado["vinculo"] if preparado["interpretar"] else None
        accion = await _interpretar(preparado) if vinculo else CONSULTA
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


async def enviar_uno():
    async with conexion() as conn:
        cola = ColaWhatsAppSQL(UnidadDeTrabajo(conn))
        mensaje = await cola.reclamar()
        if not mensaje:
            return False
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


async def procesar_lote(limite=20):
    async with conexion() as conn:
        pendientes = await ColaWhatsAppSQL(UnidadDeTrabajo(conn)).pendientes(limite)
    for entrada in pendientes:
        await procesar_entrada(entrada["id"])
    for _ in range(limite):
        if not await enviar_uno():
            break
    return {"entradas": len(pendientes)}
