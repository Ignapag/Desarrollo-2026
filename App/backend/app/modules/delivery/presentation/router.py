"""Endpoints del modulo de asignacion de repartidores (EDT 1.3).

⚠️ PENDIENTE DE PROTECCION: el modulo de Usuarios y Seguridad (EDT 1.8) esta a
cargo de otro integrante y todavia no existe, asi que estos endpoints no
validan sesion ni rol. Cuando ese modulo se integre hay que agregar la guarda
correspondiente **antes** del parametro `servicio` en cada firma:

    empleado: PersonalInterno,     # <- la guarda va primero
    servicio: ServicioDeliveryDep,

Segun el alcance: el Empleado marca el pedido listo para despacho, el
Dueno/Supervisor supervisa y reasigna, y el Repartidor ve sus pedidos y
actualiza el estado de la entrega.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencias import ServicioDeliveryDep
from app.modules.delivery.presentation.esquemas import (
    DetalleViaje,
    PropuestaAsignacion,
    ResultadoEntrega,
    ResultadoInicioViaje,
    ResultadoPlanificacionSalida,
    ViajeActivo,
)

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


@router.get("/planificacion", response_model=list[PropuestaAsignacion])
async def previsualizar(servicio: ServicioDeliveryDep) -> list[PropuestaAsignacion]:
    """Muestra que viajes se armarian, sin escribir nada en la base."""
    propuestas = await servicio.previsualizar()
    return [PropuestaAsignacion.desde_dominio(p) for p in propuestas]


@router.post("/planificacion", response_model=ResultadoPlanificacionSalida)
async def planificar(servicio: ServicioDeliveryDep) -> ResultadoPlanificacionSalida:
    """Agrupa los pedidos listos y les asigna repartidor (RF-04)."""
    resultado = await servicio.planificar_y_asignar()
    return ResultadoPlanificacionSalida.desde_dominio(resultado)


@router.get("/viajes", response_model=list[ViajeActivo])
async def viajes_activos(servicio: ServicioDeliveryDep) -> list[ViajeActivo]:
    return [ViajeActivo(**v) for v in await servicio.viajes_activos()]


@router.get("/viajes/{viaje_id}", response_model=DetalleViaje)
async def detalle_viaje(viaje_id: int, servicio: ServicioDeliveryDep) -> DetalleViaje:
    return DetalleViaje(**await servicio.detalle_viaje(viaje_id))


@router.post("/viajes/{viaje_id}/iniciar", response_model=ResultadoInicioViaje)
async def iniciar_viaje(viaje_id: int, servicio: ServicioDeliveryDep) -> ResultadoInicioViaje:
    """El repartidor sale del local: dispara la notificacion 'en camino'."""
    return ResultadoInicioViaje(**await servicio.iniciar_viaje(viaje_id))


@router.post("/envios/{envio_id}/entregar", response_model=ResultadoEntrega)
async def registrar_entrega(envio_id: int, servicio: ServicioDeliveryDep) -> ResultadoEntrega:
    """Confirma la entrega. Si era el ultimo del viaje, libera al repartidor."""
    return ResultadoEntrega(**await servicio.registrar_entrega(envio_id))


@router.get("/repartidores/{repartidor_id}/viaje", response_model=DetalleViaje | None)
async def viaje_del_repartidor(
    repartidor_id: int, servicio: ServicioDeliveryDep
) -> DetalleViaje | None:
    """Panel del repartidor: su viaje abierto, con direcciones y contactos."""
    viaje = await servicio.viaje_del_repartidor(repartidor_id)
    return DetalleViaje(**viaje) if viaje else None
