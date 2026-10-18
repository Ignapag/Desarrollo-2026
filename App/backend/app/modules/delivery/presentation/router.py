"""Endpoints protegidos del modulo de asignacion de repartidores (EDT 1.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.modules.delivery.presentation.dependencias import ServicioDeliveryDep
from app.modules.delivery.presentation.esquemas import (
    AsignacionManual,
    CorreccionEntrega,
    DetalleViaje,
    MotivoOperacion,
    PropuestaAsignacion,
    RegresoEnvio,
    ResultadoEntrega,
    ResultadoInicioViaje,
    ResultadoPlanificacionSalida,
    ViajeActivo,
)
from app.modules.usuarios.domain.entidades import ClaimsSesion, Rol
from app.modules.usuarios.presentation.dependencias import (
    AdministradorODuenio,
    PersonalInterno,
    requiere_rol,
)

PersonalLocal = Annotated[
    ClaimsSesion, Depends(requiere_rol(Rol.EMPLEADO, Rol.ADMINISTRADOR, Rol.DUENIO))
]

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


@router.get("/planificacion", response_model=list[PropuestaAsignacion])
async def previsualizar(
    sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> list[PropuestaAsignacion]:
    """Muestra que viajes se armarian, sin escribir nada en la base."""
    propuestas = await servicio.previsualizar()
    return [PropuestaAsignacion.desde_dominio(p) for p in propuestas]


@router.post("/planificacion", response_model=ResultadoPlanificacionSalida)
async def planificar(
    sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> ResultadoPlanificacionSalida:
    """Agrupa los pedidos listos y les asigna repartidor (RF-04)."""
    resultado = await servicio.planificar_y_asignar(usuario_id=sesion.usuario_id, rol=sesion.rol)
    return ResultadoPlanificacionSalida.desde_dominio(resultado)


@router.get("/viajes", response_model=list[ViajeActivo])
async def viajes_activos(
    sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> list[ViajeActivo]:
    return [
        ViajeActivo(**v)
        for v in await servicio.viajes_activos(usuario_id=sesion.usuario_id, rol=sesion.rol)
    ]


@router.get("/repartidores")
async def repartidores_disponibles(
    sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> list[dict]:
    """Repartidores activos, disponibles y sin viaje abierto para asignacion manual."""
    return await servicio.repartidores_disponibles(rol=sesion.rol)


@router.get("/viajes/{viaje_id}", response_model=DetalleViaje)
async def detalle_viaje(
    viaje_id: int, sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> DetalleViaje:
    return DetalleViaje(
        **await servicio.detalle_viaje(viaje_id, usuario_id=sesion.usuario_id, rol=sesion.rol)
    )


@router.post("/viajes/{viaje_id}/iniciar", response_model=ResultadoInicioViaje)
async def iniciar_viaje(
    viaje_id: int, sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> ResultadoInicioViaje:
    """El repartidor sale del local: dispara la notificacion 'en camino'."""
    return ResultadoInicioViaje(
        **await servicio.iniciar_viaje(viaje_id, usuario_id=sesion.usuario_id, rol=sesion.rol)
    )


@router.post("/envios/{envio_id}/entregar", response_model=ResultadoEntrega)
async def registrar_entrega(
    envio_id: int, sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> ResultadoEntrega:
    """Confirma la entrega. Si era el ultimo del viaje, libera al repartidor."""
    return ResultadoEntrega(
        **await servicio.registrar_entrega(envio_id, usuario_id=sesion.usuario_id, rol=sesion.rol)
    )


@router.get("/repartidores/{repartidor_id}/viaje", response_model=DetalleViaje | None)
async def viaje_del_repartidor(
    repartidor_id: int, sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> DetalleViaje | None:
    """Panel del repartidor: su viaje abierto, con direcciones y contactos."""
    viaje = await servicio.viaje_del_repartidor(
        repartidor_id, usuario_id=sesion.usuario_id, rol=sesion.rol
    )
    return DetalleViaje(**viaje) if viaje else None


@router.post("/pedidos/{pedido_id}/asignar")
async def asignar_pedido(
    pedido_id: int, datos: AsignacionManual, sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> dict:
    return await servicio.asignar_pedido(
        pedido_id,
        datos.repartidor_id,
        motivo=datos.motivo,
        usuario_id=sesion.usuario_id,
        rol=sesion.rol,
    )


@router.post("/envios/{envio_id}/desasignar")
async def desasignar_envio(
    envio_id: int, datos: MotivoOperacion, sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> dict:
    return await servicio.desasignar_envio(
        envio_id, motivo=datos.motivo, usuario_id=sesion.usuario_id, rol=sesion.rol
    )


@router.post("/envios/{envio_id}/fallo")
async def registrar_fallo(
    envio_id: int, datos: MotivoOperacion, sesion: PersonalInterno, servicio: ServicioDeliveryDep
) -> dict:
    return await servicio.registrar_fallo(
        envio_id, motivo=datos.motivo, usuario_id=sesion.usuario_id, rol=sesion.rol
    )


@router.post("/envios/{envio_id}/reasignar")
async def reasignar_envio(
    envio_id: int,
    datos: AsignacionManual,
    sesion: PersonalLocal,
    servicio: ServicioDeliveryDep,
) -> dict:
    return await servicio.reasignar_envio(
        envio_id,
        datos.repartidor_id,
        motivo=datos.motivo,
        usuario_id=sesion.usuario_id,
        rol=sesion.rol,
    )


@router.post("/envios/{envio_id}/regreso")
async def confirmar_regreso(
    envio_id: int, datos: RegresoEnvio, sesion: PersonalLocal, servicio: ServicioDeliveryDep
) -> dict:
    return await servicio.confirmar_regreso(
        envio_id,
        motivo=datos.motivo,
        version_esperada=datos.version_esperada,
        usuario_id=sesion.usuario_id,
        rol=sesion.rol,
    )


@router.post("/envios/{envio_id}/corregir-entrega")
async def corregir_entrega(
    envio_id: int,
    datos: CorreccionEntrega,
    sesion: AdministradorODuenio,
    servicio: ServicioDeliveryDep,
) -> dict:
    """Administracion confirma el paquete en el local y corrige la entrega registrada."""
    return await servicio.corregir_entrega(
        envio_id,
        motivo=datos.motivo,
        version_esperada=datos.version_esperada,
        regreso_confirmado=datos.regreso_confirmado,
        usuario_id=sesion.usuario_id,
        rol=sesion.rol,
    )
