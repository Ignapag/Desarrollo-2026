"""Entidades y algoritmos del dominio de delivery.

Todo lo de este archivo es logica pura: no toca la base ni FastAPI, y por eso
se puede probar sin infraestructura.

Cubre las tareas 9 y 10 del cronograma:
  - agrupar_pedidos()   : agrupacion geografica (RF-04)
  - elegir_repartidor() : asignacion al disponible mas cercano (RF-04)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt

#: Radio de la Tierra en kilometros.
RADIO_TIERRA_KM = 6371.0


class EstadoViaje(StrEnum):
    PLANIFICADO = "PLANIFICADO"
    EN_RUTA = "EN_RUTA"
    FINALIZADO = "FINALIZADO"
    CANCELADO = "CANCELADO"


class EstadoEnvio(StrEnum):
    PENDIENTE = "PENDIENTE"
    ASIGNADO = "ASIGNADO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    FALLIDO = "FALLIDO"


class EstadoRepartidor(StrEnum):
    DISPONIBLE = "DISPONIBLE"
    EN_RUTA = "EN_RUTA"
    FUERA_DE_SERVICIO = "FUERA_DE_SERVICIO"


def distancia_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en linea recta entre dos coordenadas (haversine).

    Replica la funcion distancia_km() de la base para poder calcular sin
    ida y vuelta a PostgreSQL. Las pruebas verifican que ambas coincidan.
    """
    lat1_r, lat2_r = radians(lat1), radians(lat2)
    dif_lat = radians(lat2 - lat1)
    dif_lng = radians(lng2 - lng1)

    a = sin(dif_lat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dif_lng / 2) ** 2
    return round(RADIO_TIERRA_KM * 2 * asin(sqrt(a)), 3)


@dataclass(slots=True, frozen=True)
class PedidoParaDespachar:
    """Pedido listo, esperando que se le asigne un repartidor."""

    pedido_id: int
    numero: int
    zona_id: int | None
    zona_nombre: str | None
    lat: float | None
    lng: float | None
    creado_en: datetime

    @property
    def tiene_ubicacion(self) -> bool:
        return self.lat is not None and self.lng is not None

    def distancia_a(self, otro: PedidoParaDespachar) -> float | None:
        if not (self.tiene_ubicacion and otro.tiene_ubicacion):
            return None
        return distancia_km(self.lat, self.lng, otro.lat, otro.lng)  # type: ignore[arg-type]


@dataclass(slots=True, frozen=True)
class RepartidorDisponible:
    repartidor_id: int
    nombre: str
    lat: float | None
    lng: float | None

    @property
    def tiene_ubicacion(self) -> bool:
        return self.lat is not None and self.lng is not None


@dataclass(slots=True)
class GrupoDeReparto:
    """Conjunto de pedidos que sale en un mismo viaje."""

    pedidos: list[PedidoParaDespachar] = field(default_factory=list)

    @property
    def cantidad(self) -> int:
        return len(self.pedidos)

    @property
    def zona_id(self) -> int | None:
        return self.pedidos[0].zona_id if self.pedidos else None

    @property
    def punto_de_referencia(self) -> tuple[float, float] | None:
        """Ubicacion del primer pedido: es el punto al que se despacha primero."""
        for pedido in self.pedidos:
            if pedido.tiene_ubicacion:
                return (pedido.lat, pedido.lng)  # type: ignore[return-value]
        return None

    def distancia_desde(self, repartidor: RepartidorDisponible) -> float | None:
        referencia = self.punto_de_referencia
        if referencia is None or not repartidor.tiene_ubicacion:
            return None
        return distancia_km(repartidor.lat, repartidor.lng, *referencia)  # type: ignore[arg-type]


# ---------------------------------------------------------------------
# Tarea 9: agrupacion geografica
# ---------------------------------------------------------------------

def agrupar_pedidos(
    pedidos: list[PedidoParaDespachar],
    *,
    radio_km: float,
    max_por_viaje: int = 2,
) -> list[GrupoDeReparto]:
    """Agrupa pedidos cercanos para que salgan en el mismo viaje.

    Regla acordada con el cliente: dos pedidos viajan juntos si estan en la
    **misma zona de cobertura** y a menos de `radio_km` entre si.

    El recorrido arranca siempre por el pedido mas antiguo. Esa prioridad
    evita que un pedido quede postergado indefinidamente porque el algoritmo
    encuentra mejores pares entre los mas nuevos.

    Un pedido sin ningun vecino cercano sale solo: agrupar es una
    optimizacion, no una condicion para despachar.
    """
    if max_por_viaje < 1:
        raise ValueError("max_por_viaje debe ser al menos 1")

    pendientes = sorted(pedidos, key=lambda p: (p.creado_en, p.pedido_id))
    grupos: list[GrupoDeReparto] = []

    while pendientes:
        ancla = pendientes.pop(0)
        grupo = GrupoDeReparto(pedidos=[ancla])

        while grupo.cantidad < max_por_viaje:
            companiero = _vecino_mas_cercano(ancla, pendientes, radio_km)
            if companiero is None:
                break
            pendientes.remove(companiero)
            grupo.pedidos.append(companiero)

        grupos.append(grupo)

    return grupos


def _vecino_mas_cercano(
    ancla: PedidoParaDespachar,
    candidatos: list[PedidoParaDespachar],
    radio_km: float,
) -> PedidoParaDespachar | None:
    """Pedido mas cercano al ancla que cumple zona y radio."""
    mejor: PedidoParaDespachar | None = None
    mejor_distancia = float("inf")

    for candidato in candidatos:
        if not _misma_zona(ancla, candidato):
            continue
        distancia = ancla.distancia_a(candidato)
        if distancia is None or distancia > radio_km:
            continue
        if distancia < mejor_distancia:
            mejor, mejor_distancia = candidato, distancia

    return mejor


def _misma_zona(uno: PedidoParaDespachar, otro: PedidoParaDespachar) -> bool:
    """Dos pedidos sin zona resuelta nunca se agrupan: no hay como saber si
    estan cerca de verdad."""
    if uno.zona_id is None or otro.zona_id is None:
        return False
    return uno.zona_id == otro.zona_id


# ---------------------------------------------------------------------
# Tarea 10: asignacion automatica
# ---------------------------------------------------------------------

def elegir_repartidor(
    grupo: GrupoDeReparto,
    repartidores: list[RepartidorDisponible],
    *,
    radio_busqueda_km: float | None = None,
) -> RepartidorDisponible | None:
    """Elige el repartidor disponible mas cercano al primer domicilio.

    Devuelve None si no hay repartidores, o si ninguno esta dentro del radio
    de busqueda. Un repartidor sin ubicacion conocida se considera solo
    cuando ninguno tiene ubicacion: es preferible despachar con un criterio
    debil que dejar el pedido sin asignar.
    """
    if not repartidores:
        return None

    con_ubicacion = [r for r in repartidores if r.tiene_ubicacion]
    if not con_ubicacion or grupo.punto_de_referencia is None:
        return repartidores[0]

    candidatos: list[tuple[float, RepartidorDisponible]] = []
    for repartidor in con_ubicacion:
        distancia = grupo.distancia_desde(repartidor)
        if distancia is None:
            continue
        if radio_busqueda_km is not None and distancia > radio_busqueda_km:
            continue
        candidatos.append((distancia, repartidor))

    if not candidatos:
        return None

    # Ante empate, el de menor id: hace la asignacion determinista y repetible.
    candidatos.sort(key=lambda par: (par[0], par[1].repartidor_id))
    return candidatos[0][1]


@dataclass(slots=True)
class AsignacionPropuesta:
    """Resultado de planificar: un grupo con su repartidor elegido."""

    grupo: GrupoDeReparto
    repartidor: RepartidorDisponible | None
    distancia_km: float | None = None

    @property
    def asignable(self) -> bool:
        return self.repartidor is not None


def planificar(
    pedidos: list[PedidoParaDespachar],
    repartidores: list[RepartidorDisponible],
    *,
    radio_agrupacion_km: float,
    radio_busqueda_km: float | None = None,
    max_por_viaje: int = 2,
) -> list[AsignacionPropuesta]:
    """Arma los grupos y les asigna repartidor, sin tocar la base.

    Cada repartidor se usa una sola vez: al quedar asignado a un viaje deja
    de estar disponible para el resto de la planificacion.
    """
    grupos = agrupar_pedidos(
        pedidos, radio_km=radio_agrupacion_km, max_por_viaje=max_por_viaje
    )

    libres = list(repartidores)
    propuestas: list[AsignacionPropuesta] = []

    for grupo in grupos:
        elegido = elegir_repartidor(grupo, libres, radio_busqueda_km=radio_busqueda_km)
        distancia = grupo.distancia_desde(elegido) if elegido else None
        if elegido is not None:
            libres.remove(elegido)
        propuestas.append(
            AsignacionPropuesta(grupo=grupo, repartidor=elegido, distancia_km=distancia)
        )

    return propuestas
