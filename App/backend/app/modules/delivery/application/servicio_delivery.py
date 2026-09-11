"""Casos de uso del modulo de asignacion de repartidores (EDT 1.3).

Orquesta el algoritmo del dominio con la base: arma los viajes, los despacha
y registra las entregas, dejando rastro en el historial de estados y en
auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.delivery.domain.entidades import (
    AsignacionPropuesta,
    EstadoEnvio,
    EstadoRepartidor,
    EstadoViaje,
    planificar,
)
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL

MAX_POR_VIAJE_POR_DEFECTO = 2
RADIO_AGRUPACION_POR_DEFECTO = 1.5
RADIO_BUSQUEDA_POR_DEFECTO = 10.0


class AccionesDelivery:
    VIAJE_ASIGNADO = "VIAJE_ASIGNADO"
    VIAJE_INICIADO = "VIAJE_INICIADO"
    ENVIO_ENTREGADO = "ENVIO_ENTREGADO"
    VIAJE_FINALIZADO = "VIAJE_FINALIZADO"


@dataclass(slots=True)
class ViajeCreado:
    viaje_id: int
    repartidor_id: int
    repartidor_nombre: str
    pedidos: list[int]
    distancia_km: float | None


@dataclass(slots=True)
class ResultadoPlanificacion:
    viajes: list[ViajeCreado]
    sin_asignar: list[int]
    pedidos_evaluados: int
    repartidores_disponibles: int


class ServicioDelivery:
    def __init__(self, uow: UnidadDeTrabajo, repositorio: RepositorioDeliverySQL) -> None:
        self.uow = uow
        self.repo = repositorio

    # ------------------------------ planificacion ---------------------

    async def _parametros(self) -> tuple[float, float, int]:
        radio_agrupacion = float(
            await self.repo.parametro(
                "delivery.radio_agrupacion_km", str(RADIO_AGRUPACION_POR_DEFECTO)
            )
        )
        radio_busqueda = float(
            await self.repo.parametro(
                "delivery.radio_busqueda_repartidor_km", str(RADIO_BUSQUEDA_POR_DEFECTO)
            )
        )
        max_por_viaje = int(
            await self.repo.parametro(
                "delivery.pedidos_por_viaje", str(MAX_POR_VIAJE_POR_DEFECTO)
            )
        )
        return radio_agrupacion, radio_busqueda, max_por_viaje

    async def previsualizar(self) -> list[AsignacionPropuesta]:
        """Calcula la asignacion sin escribir nada.

        Sirve para que el panel muestre que va a pasar antes de confirmarlo.
        """
        radio_agrupacion, radio_busqueda, max_por_viaje = await self._parametros()
        pedidos = await self.repo.pedidos_para_despachar()
        repartidores = await self.repo.repartidores_disponibles()

        return planificar(
            pedidos,
            repartidores,
            radio_agrupacion_km=radio_agrupacion,
            radio_busqueda_km=radio_busqueda,
            max_por_viaje=max_por_viaje,
        )

    async def planificar_y_asignar(
        self, *, usuario_id: int | None = None
    ) -> ResultadoPlanificacion:
        """Arma los viajes y los persiste (RF-04).

        Se ejecuta cuando hay pedidos listos para despacho. Los pedidos que no
        consiguen repartidor quedan esperando a la proxima corrida.
        """
        propuestas = await self.previsualizar()

        viajes: list[ViajeCreado] = []
        sin_asignar: list[int] = []
        evaluados = sum(p.grupo.cantidad for p in propuestas)
        disponibles = sum(1 for p in propuestas if p.asignable)

        for propuesta in propuestas:
            if not propuesta.asignable:
                sin_asignar.extend(p.pedido_id for p in propuesta.grupo.pedidos)
                continue

            repartidor = propuesta.repartidor
            assert repartidor is not None

            viaje_id = await self.repo.crear_viaje(
                repartidor.repartidor_id, asignado_por=usuario_id, automatica=True
            )

            for orden, pedido in enumerate(propuesta.grupo.pedidos, start=1):
                await self.repo.asignar_envio(
                    pedido_id=pedido.pedido_id,
                    viaje_id=viaje_id,
                    zona_id=pedido.zona_id,
                    orden=orden,
                    distancia_km=propuesta.distancia_km if orden == 1 else None,
                )

            await self.repo.cambiar_estado_repartidor(
                repartidor.repartidor_id, EstadoRepartidor.EN_RUTA.value
            )

            pedidos_ids = [p.pedido_id for p in propuesta.grupo.pedidos]
            await auditoria.registrar(
                self.uow,
                accion=AccionesDelivery.VIAJE_ASIGNADO,
                entidad="viaje",
                entidad_id=viaje_id,
                usuario_id=usuario_id,
                datos={
                    "repartidor_id": repartidor.repartidor_id,
                    "pedidos": pedidos_ids,
                    "distancia_km": propuesta.distancia_km,
                    "automatica": True,
                },
            )

            viajes.append(
                ViajeCreado(
                    viaje_id=viaje_id,
                    repartidor_id=repartidor.repartidor_id,
                    repartidor_nombre=repartidor.nombre,
                    pedidos=pedidos_ids,
                    distancia_km=propuesta.distancia_km,
                )
            )

        return ResultadoPlanificacion(
            viajes=viajes,
            sin_asignar=sin_asignar,
            pedidos_evaluados=evaluados,
            repartidores_disponibles=disponibles,
        )

    # ------------------------------ operacion -------------------------

    async def iniciar_viaje(self, viaje_id: int, *, usuario_id: int | None = None) -> dict:
        """El repartidor sale del local: todo el viaje pasa a 'en camino'.

        Es el disparador de la notificacion de WhatsApp al cliente (RF-10),
        que envia el modulo del bot cuando se integre.
        """
        viaje = await self.repo.viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        if viaje["estado"] != EstadoViaje.PLANIFICADO.value:
            raise ReglaDeNegocio(
                f"El viaje ya esta en estado {viaje['estado']}; solo se puede iniciar "
                "un viaje planificado"
            )

        await self.repo.cambiar_estado_viaje(viaje_id, EstadoViaje.EN_RUTA.value)
        pedidos = await self.repo.cambiar_estado_envios_del_viaje(
            viaje_id, EstadoEnvio.EN_CAMINO.value
        )
        for pedido_id in pedidos:
            await self.repo.cambiar_estado_pedido(
                pedido_id, "EN_CAMINO", usuario_id=usuario_id, observacion=f"Viaje {viaje_id}"
            )

        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.VIAJE_INICIADO,
            entidad="viaje",
            entidad_id=viaje_id,
            usuario_id=usuario_id,
            datos={"pedidos": pedidos},
        )
        return {"viaje_id": viaje_id, "pedidos_en_camino": pedidos}

    async def registrar_entrega(self, envio_id: int, *, usuario_id: int | None = None) -> dict:
        """Marca un envio como entregado.

        Cuando no quedan envios pendientes, el viaje se cierra y el repartidor
        vuelve a estar disponible para la proxima asignacion.
        """
        envio = await self.repo.envio(envio_id)
        if envio is None:
            raise NoEncontrado("El envio no existe")
        if envio["estado"] == EstadoEnvio.ENTREGADO.value:
            raise ReglaDeNegocio("El envio ya figura como entregado")
        if envio["viaje_id"] is None:
            raise ReglaDeNegocio("El envio todavia no esta asignado a un viaje")

        await self.repo.cambiar_estado_envio(envio_id, EstadoEnvio.ENTREGADO.value)
        await self.repo.cambiar_estado_pedido(
            envio["pedido_id"], "ENTREGADO", usuario_id=usuario_id
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.ENVIO_ENTREGADO,
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"pedido_id": envio["pedido_id"], "viaje_id": envio["viaje_id"]},
        )

        viaje_finalizado = False
        if not await self.repo.quedan_envios_pendientes(envio["viaje_id"]):
            await self.repo.cambiar_estado_viaje(
                envio["viaje_id"], EstadoViaje.FINALIZADO.value
            )
            await self.repo.cambiar_estado_repartidor(
                envio["repartidor_id"], EstadoRepartidor.DISPONIBLE.value
            )
            await auditoria.registrar(
                self.uow,
                accion=AccionesDelivery.VIAJE_FINALIZADO,
                entidad="viaje",
                entidad_id=envio["viaje_id"],
                usuario_id=usuario_id,
            )
            viaje_finalizado = True

        return {
            "envio_id": envio_id,
            "pedido_id": envio["pedido_id"],
            "viaje_finalizado": viaje_finalizado,
        }

    # ------------------------------ consultas -------------------------

    async def viajes_activos(self) -> list[dict]:
        return await self.repo.viajes_activos()

    async def detalle_viaje(self, viaje_id: int) -> dict:
        viaje = await self.repo.viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        return {**viaje, "envios": await self.repo.envios_del_viaje(viaje_id)}

    async def viaje_del_repartidor(self, repartidor_id: int) -> dict | None:
        abierto = await self.repo.viaje_abierto_de(repartidor_id)
        if abierto is None:
            return None
        return await self.detalle_viaje(abierto["id"])
