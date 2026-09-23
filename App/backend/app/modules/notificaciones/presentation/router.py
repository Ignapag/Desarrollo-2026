"""Endpoints del modulo de Notificaciones / Bot de WhatsApp (EDT 1.7).

Alcance de este modulo: plantillas, encolado y el estado de cada envio. El
envio real por WhatsApp Cloud API a traves de n8n (tarea de integracion,
fuera de este alcance) no esta incluido: `EnviadorSimulado`
(infrastructure/enviadores.py) deja el flujo funcionando de punta a punta
para desarrollo y pruebas, y documenta el puerto que esa integracion debe
implementar sin tocar el resto del modulo.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencias import AdministradorODuenio, PersonalInterno, ServicioNotificacionesDep
from app.modules.notificaciones.presentation.esquemas import (
    ModificarPlantillaEntrada,
    NotificacionSalida,
    PlantillaEntrada,
    PlantillaSalida,
    ResultadoProcesamiento,
)

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])


# ------------------------------ CU_BOT_04 a 07: plantillas -----------------

@router.get("/plantillas", response_model=list[PlantillaSalida])
async def buscar_plantillas(
    _sesion: AdministradorODuenio,
    servicio: ServicioNotificacionesDep,
    nombre: str | None = None,
    evento: str | None = None,
    activa: bool | None = None,
) -> list[PlantillaSalida]:
    filas = await servicio.buscar_plantillas(nombre=nombre, evento=evento, activa=activa)
    return [PlantillaSalida(**f) for f in filas]


@router.post("/plantillas", response_model=PlantillaSalida, status_code=201)
async def registrar_plantilla(
    datos: PlantillaEntrada, sesion: AdministradorODuenio, servicio: ServicioNotificacionesDep
) -> PlantillaSalida:
    creada = await servicio.registrar_plantilla(
        clave=datos.clave,
        nombre=datos.nombre,
        cuerpo=datos.cuerpo,
        activa=datos.activa,
        ejecutor_id=sesion.usuario_id,
    )
    return PlantillaSalida(**creada)


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaSalida)
async def modificar_plantilla(
    plantilla_id: int,
    datos: ModificarPlantillaEntrada,
    sesion: AdministradorODuenio,
    servicio: ServicioNotificacionesDep,
) -> PlantillaSalida:
    actualizada = await servicio.modificar_plantilla(
        plantilla_id,
        nombre=datos.nombre,
        cuerpo=datos.cuerpo,
        activa=datos.activa,
        ejecutor_id=sesion.usuario_id,
    )
    return PlantillaSalida(**actualizada)


@router.post("/plantillas/{plantilla_id}/desactivar", response_model=PlantillaSalida)
async def desactivar_plantilla(
    plantilla_id: int, sesion: AdministradorODuenio, servicio: ServicioNotificacionesDep
) -> PlantillaSalida:
    desactivada = await servicio.desactivar_plantilla(plantilla_id, ejecutor_id=sesion.usuario_id)
    return PlantillaSalida(**desactivada)


# ------------------------------ consulta y procesamiento -------------------

@router.get("", response_model=list[NotificacionSalida])
async def listar_notificaciones(
    _sesion: PersonalInterno,
    servicio: ServicioNotificacionesDep,
    pedido_id: int | None = None,
    estado: str | None = None,
) -> list[NotificacionSalida]:
    notificaciones = await servicio.listar(pedido_id=pedido_id, estado=estado)
    return [NotificacionSalida(**n) for n in notificaciones]


@router.post("/procesar", response_model=ResultadoProcesamiento)
async def procesar_pendientes(
    _sesion: AdministradorODuenio, servicio: ServicioNotificacionesDep
) -> ResultadoProcesamiento:
    """Dispara el envio de las notificaciones PENDIENTE.

    Manual por ahora, para desarrollo y demo. Cuando se integre el canal
    real, esto puede quedar igual (llamado desde un boton del panel) o
    dispararse solo desde un job/webhook: `procesar_pendientes()` no
    cambia.
    """
    resultado = await servicio.procesar_pendientes()
    return ResultadoProcesamiento(**resultado)
