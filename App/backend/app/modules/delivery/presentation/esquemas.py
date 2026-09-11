"""Esquemas Pydantic del modulo de delivery."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.modules.delivery.application.servicio_delivery import (
    ResultadoPlanificacion,
    ViajeCreado,
)
from app.modules.delivery.domain.entidades import AsignacionPropuesta


class PedidoEnGrupo(BaseModel):
    pedido_id: int
    numero: int
    zona_nombre: str | None
    lat: float | None
    lng: float | None


class PropuestaAsignacion(BaseModel):
    """Lo que se armaria si se confirma la planificacion."""

    pedidos: list[PedidoEnGrupo]
    repartidor_id: int | None
    repartidor_nombre: str | None
    distancia_km: float | None
    asignable: bool
    motivo: str | None = None

    @classmethod
    def desde_dominio(cls, propuesta: AsignacionPropuesta) -> PropuestaAsignacion:
        return cls(
            pedidos=[
                PedidoEnGrupo(
                    pedido_id=p.pedido_id,
                    numero=p.numero,
                    zona_nombre=p.zona_nombre,
                    lat=p.lat,
                    lng=p.lng,
                )
                for p in propuesta.grupo.pedidos
            ],
            repartidor_id=propuesta.repartidor.repartidor_id if propuesta.repartidor else None,
            repartidor_nombre=propuesta.repartidor.nombre if propuesta.repartidor else None,
            distancia_km=propuesta.distancia_km,
            asignable=propuesta.asignable,
            motivo=None if propuesta.asignable else "No hay repartidor disponible en el radio",
        )


class ViajeCreadoSalida(BaseModel):
    viaje_id: int
    repartidor_id: int
    repartidor_nombre: str
    pedidos: list[int]
    distancia_km: float | None


class ResultadoPlanificacionSalida(BaseModel):
    viajes: list[ViajeCreadoSalida]
    sin_asignar: list[int]
    pedidos_evaluados: int
    repartidores_disponibles: int

    @classmethod
    def desde_dominio(cls, resultado: ResultadoPlanificacion) -> ResultadoPlanificacionSalida:
        def salida(v: ViajeCreado) -> ViajeCreadoSalida:
            return ViajeCreadoSalida(
                viaje_id=v.viaje_id,
                repartidor_id=v.repartidor_id,
                repartidor_nombre=v.repartidor_nombre,
                pedidos=v.pedidos,
                distancia_km=v.distancia_km,
            )

        return cls(
            viajes=[salida(v) for v in resultado.viajes],
            sin_asignar=resultado.sin_asignar,
            pedidos_evaluados=resultado.pedidos_evaluados,
            repartidores_disponibles=resultado.repartidores_disponibles,
        )


class ViajeActivo(BaseModel):
    id: int
    estado: str
    creado_en: datetime
    salida_en: datetime | None
    repartidor_id: int
    repartidor_nombre: str
    cantidad_envios: int


class EnvioDelViaje(BaseModel):
    id: int
    pedido_id: int
    numero: int
    estado: str
    orden_en_viaje: int
    distancia_km: float | None
    entregado_en: datetime | None
    calle: str | None
    altura: str | None
    piso_depto: str | None
    referencia: str | None
    zona_nombre: str | None
    cliente_nombre: str
    # El alcance lo permite solo al repartidor asignado a ese pedido
    telefono_cliente: str


class DetalleViaje(BaseModel):
    id: int
    estado: str
    creado_en: datetime
    salida_en: datetime | None
    retorno_en: datetime | None
    repartidor_id: int
    repartidor_nombre: str
    envios: list[EnvioDelViaje]


class ResultadoInicioViaje(BaseModel):
    viaje_id: int
    pedidos_en_camino: list[int]


class ResultadoEntrega(BaseModel):
    envio_id: int
    pedido_id: int
    viaje_finalizado: bool
