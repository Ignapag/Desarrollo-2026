"""Casos de uso del modulo de asignacion de repartidores (EDT 1.3).

Orquesta el algoritmo del dominio con la base: arma los viajes, los despacha
y registra las entregas, dejando rastro en el historial de estados y en
auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.errores import NoEncontrado, ReglaDeNegocio, SinPermiso
from app.modules.delivery.domain.entidades import (
    AsignacionPropuesta,
    EstadoRepartidor,
    planificar,
)
from app.modules.delivery.infrastructure.repositorio_sql import RepositorioDeliverySQL
from app.modules.pedidos.domain.entidades import EstadoPedido

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


class AutoridadPedidos(Protocol):
    async def cambiar_estado(self, pedido_id: int, nuevo: EstadoPedido, **opciones) -> dict: ...


class ServicioDelivery:
    def __init__(
        self, uow: UnidadDeTrabajo, repositorio: RepositorioDeliverySQL, pedidos: AutoridadPedidos
    ) -> None:
        self.uow = uow
        self.repo = repositorio
        self.pedidos = pedidos

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
            await self.repo.parametro("delivery.pedidos_por_viaje", str(MAX_POR_VIAJE_POR_DEFECTO))
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
        self,
        *,
        usuario_id: int | None = None,
        rol: str | None = None,
        autorizado: bool | None = None,
    ) -> ResultadoPlanificacion:
        """Arma los viajes y los persiste (RF-04).

        Se ejecuta cuando hay pedidos listos para despacho. Los pedidos que no
        consiguen repartidor quedan esperando a la proxima corrida.
        """
        self._personal(rol, autorizado=autorizado)
        if rol == "REPARTIDOR":
            raise SinPermiso("La planificacion global no se limita a tu propio viaje")
        radio_agrupacion, radio_busqueda, max_por_viaje = await self._parametros()
        candidatos = await self.repo.pedidos_para_despachar(bloquear=True)
        repartidores = await self.repo.repartidores_disponibles(bloquear=True)
        propuestas = planificar(
            candidatos,
            repartidores,
            radio_agrupacion_km=radio_agrupacion,
            radio_busqueda_km=radio_busqueda,
            max_por_viaje=max_por_viaje,
        )

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

    @staticmethod
    def _personal(rol: str | None, *, autorizado: bool | None = None) -> None:
        permitido = rol is None or rol in {"EMPLEADO", "ADMINISTRADOR", "DUENIO"}
        if not (permitido if autorizado is None else autorizado):
            raise SinPermiso("Esta operacion requiere personal del local")

    @staticmethod
    def _autorizar(viaje: dict, usuario_id: int | None, rol: str | None) -> None:
        if rol == "REPARTIDOR" and viaje["repartidor_id"] != usuario_id:
            raise SinPermiso("Solo podes operar tu propio viaje")
        if rol is not None and rol not in {"REPARTIDOR", "EMPLEADO", "ADMINISTRADOR", "DUENIO"}:
            raise SinPermiso("No tenes acceso al reparto")

    async def iniciar_viaje(
        self, viaje_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        viaje = await self.repo.bloquear_viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        self._autorizar(viaje, usuario_id, rol)
        if viaje["estado"] != "PLANIFICADO" or viaje["salida_en"] is not None:
            raise ReglaDeNegocio("Solo se puede iniciar un viaje planificado sin salida")
        envios = await self.repo.envios_del_viaje(viaje_id)
        if not envios:
            raise ReglaDeNegocio("El viaje no tiene envios asignados")
        for envio in envios:
            pedido = await self.repo.pedido_asignable(envio["pedido_id"])
            if (
                envio["estado"] != "ASIGNADO"
                or pedido["estado"] != "LISTO"
                or pedido["tipo_entrega"] != "DELIVERY"
            ):
                raise ReglaDeNegocio("Todos los pedidos deben ser delivery listo y asignado")
        await self.repo.cambiar_estado_viaje(viaje_id, "EN_RUTA")
        ids = await self.repo.cambiar_estado_envios_del_viaje(viaje_id, "EN_CAMINO")
        for pedido_id in ids:
            await self.pedidos.cambiar_estado(
                pedido_id,
                EstadoPedido.EN_CAMINO,
                usuario_id=usuario_id,
                motivo=f"Salida del viaje {viaje_id}",
                estado_esperado="LISTO",
                origen="DELIVERY",
                rol=rol,
            )
        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.VIAJE_INICIADO,
            entidad="viaje",
            entidad_id=viaje_id,
            usuario_id=usuario_id,
            datos={"pedidos": ids},
        )
        return {"viaje_id": viaje_id, "pedidos_en_camino": ids}

    async def _envio_bloqueado(
        self, envio_id: int, usuario_id: int | None, rol: str | None
    ) -> tuple[dict, dict]:
        previo = await self.repo.envio(envio_id)
        if previo is None:
            raise NoEncontrado("El envio no existe")
        if previo["viaje_id"] is None:
            raise ReglaDeNegocio("El envio no esta asignado a un viaje")
        viaje = await self.repo.bloquear_viaje(previo["viaje_id"])
        self._autorizar(viaje, usuario_id, rol)
        envio = await self.repo.envio(envio_id)
        if envio["viaje_id"] != previo["viaje_id"]:
            raise ReglaDeNegocio("La asignacion cambio; actualiza el viaje")
        return envio, viaje

    async def registrar_entrega(
        self, envio_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if (
            envio["estado"] != "EN_CAMINO"
            or viaje["estado"] != "EN_RUTA"
            or viaje["salida_en"] is None
        ):
            raise ReglaDeNegocio("La entrega requiere un envio en camino y salida real del viaje")
        await self.repo.cambiar_estado_envio(envio_id, "ENTREGADO")
        await self.pedidos.cambiar_estado(
            envio["pedido_id"],
            EstadoPedido.ENTREGADO,
            usuario_id=usuario_id,
            estado_esperado="EN_CAMINO",
            origen="DELIVERY",
            rol=rol,
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.ENVIO_ENTREGADO,
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"pedido_id": envio["pedido_id"], "viaje_id": envio["viaje_id"]},
        )
        cerrado = await self._cerrar_si_resuelto(viaje, usuario_id)
        return {"envio_id": envio_id, "pedido_id": envio["pedido_id"], "viaje_finalizado": cerrado}

    async def _cerrar_si_resuelto(self, viaje: dict, usuario_id: int | None) -> bool:
        # Un fallo sigue ocupando al repartidor hasta confirmar el regreso al local.
        envios = await self.repo.envios_del_viaje(viaje["id"])
        if any(e["estado"] != "ENTREGADO" for e in envios):
            return False
        estado = "FINALIZADO" if viaje["salida_en"] else "CANCELADO"
        await self.repo.cambiar_estado_viaje(viaje["id"], estado)
        await self.repo.cambiar_estado_repartidor(viaje["repartidor_id"], "DISPONIBLE")
        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.VIAJE_FINALIZADO,
            entidad="viaje",
            entidad_id=viaje["id"],
            usuario_id=usuario_id,
        )
        return True

    async def desasignar_envio(
        self,
        envio_id: int,
        *,
        motivo: str,
        usuario_id: int | None = None,
        rol: str | None = None,
        autorizado: bool | None = None,
    ) -> dict:
        self._personal(rol, autorizado=autorizado)
        if not motivo.strip():
            raise ReglaDeNegocio("La desasignacion requiere un motivo")
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if viaje["estado"] != "PLANIFICADO" or viaje["salida_en"] or envio["estado"] != "ASIGNADO":
            raise ReglaDeNegocio("Solo se puede desasignar antes de la salida")
        await self.repo.desenganchar_envio(envio_id, motivo.strip())
        await self._cerrar_si_resuelto(viaje, usuario_id)
        await auditoria.registrar(
            self.uow,
            accion="ENVIO_DESASIGNADO",
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"viaje_id": viaje["id"], "motivo": motivo, "envio_anterior": envio},
        )
        return {"envio_id": envio_id, "pedido_id": envio["pedido_id"], "viaje_id": None}

    async def asignar_pedido(
        self,
        pedido_id: int,
        repartidor_id: int,
        *,
        motivo: str,
        usuario_id: int | None = None,
        rol: str | None = None,
        autorizado: bool | None = None,
    ) -> dict:
        self._personal(rol, autorizado=autorizado)
        self._autorizar({"repartidor_id": repartidor_id}, usuario_id, rol)
        if not motivo.strip():
            raise ReglaDeNegocio("La asignacion requiere un motivo")
        pedido = await self.repo.pedido_asignable(pedido_id)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        if pedido["estado"] != "LISTO" or pedido["tipo_entrega"] != "DELIVERY":
            raise ReglaDeNegocio("Solo se puede asignar un delivery listo")
        existente = await self.repo.envio_del_pedido(pedido_id)
        recuperado = bool(
            existente
            and existente["estado"] == "ENTREGADO"
            and existente["estado_viaje"] == "FINALIZADO"
        )
        if existente and existente["viaje_id"] is not None and not recuperado:
            raise ReglaDeNegocio("Desasigna el envio antes de volver a asignarlo")
        disponibles = await self.repo.repartidores_disponibles(bloquear=True)
        if not any(r.repartidor_id == repartidor_id for r in disponibles):
            raise ReglaDeNegocio("El repartidor no esta disponible")
        if recuperado:
            await auditoria.registrar(
                self.uow,
                accion="ENVIO_RECUPERADO",
                entidad="envio",
                entidad_id=existente["id"],
                usuario_id=usuario_id,
                datos={
                    "viaje_anterior_id": existente["viaje_id"],
                    "motivo": motivo,
                    "envio_anterior": existente,
                },
            )
            await self.repo.desenganchar_envio(existente["id"], motivo)
        viaje_id = await self.repo.crear_viaje(
            repartidor_id, asignado_por=usuario_id, automatica=False
        )
        envio_id = await self.repo.asignar_envio(
            pedido_id=pedido_id,
            viaje_id=viaje_id,
            zona_id=pedido["zona_id"],
            orden=1,
            distancia_km=None,
        )
        await self.repo.cambiar_estado_repartidor(repartidor_id, "EN_RUTA")
        await auditoria.registrar(
            self.uow,
            accion=AccionesDelivery.VIAJE_ASIGNADO,
            entidad="viaje",
            entidad_id=viaje_id,
            usuario_id=usuario_id,
            datos={"pedido_id": pedido_id, "motivo": motivo, "automatica": False},
        )
        return {"envio_id": envio_id, "pedido_id": pedido_id, "viaje_id": viaje_id}

    async def reasignar_envio(
        self,
        envio_id: int,
        repartidor_id: int,
        *,
        motivo: str,
        usuario_id: int | None = None,
        rol: str | None = None,
        autorizado: bool | None = None,
    ) -> dict:
        liberado = await self.desasignar_envio(
            envio_id, motivo=motivo, usuario_id=usuario_id, rol=rol, autorizado=autorizado
        )
        return await self.asignar_pedido(
            liberado["pedido_id"],
            repartidor_id,
            motivo=motivo,
            usuario_id=usuario_id,
            rol=rol,
            autorizado=autorizado,
        )

    async def registrar_fallo(
        self, envio_id: int, *, motivo: str, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        if not motivo.strip():
            raise ReglaDeNegocio("El fallo requiere un motivo")
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if envio["estado"] != "EN_CAMINO" or viaje["estado"] != "EN_RUTA" or not viaje["salida_en"]:
            raise ReglaDeNegocio("Solo un envio en camino puede fallar")
        await self.repo.registrar_fallo(envio_id, motivo.strip())
        await auditoria.registrar(
            self.uow,
            accion="ENVIO_FALLIDO",
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"motivo": motivo, "viaje_id": viaje["id"]},
        )
        return {"envio_id": envio_id, "pedido_id": envio["pedido_id"], "viaje_id": viaje["id"]}

    async def confirmar_regreso(
        self,
        envio_id: int,
        *,
        motivo: str,
        version_esperada: int,
        usuario_id: int | None = None,
        rol: str | None = None,
        autorizado: bool | None = None,
    ) -> dict:
        self._personal(rol, autorizado=autorizado)
        if not motivo.strip():
            raise ReglaDeNegocio("El regreso requiere un motivo")
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if envio["estado"] != "FALLIDO" or viaje["estado"] != "EN_RUTA":
            raise ReglaDeNegocio("El regreso requiere un envio fallido en ruta")
        await self.repo.desenganchar_envio(envio_id, motivo.strip())
        await self.pedidos.cambiar_estado(
            envio["pedido_id"],
            EstadoPedido.LISTO,
            usuario_id=usuario_id,
            motivo=motivo,
            version_esperada=version_esperada,
            estado_esperado="EN_CAMINO",
            origen="DELIVERY",
            rol=rol,
            correccion=True,
            permitir_correccion=autorizado,
        )
        await self._cerrar_si_resuelto(viaje, usuario_id)
        await auditoria.registrar(
            self.uow,
            accion="ENVIO_REGRESADO",
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"motivo": motivo, "viaje_id": viaje["id"], "envio_anterior": envio},
        )
        return {"envio_id": envio_id, "pedido_id": envio["pedido_id"], "viaje_id": None}

    async def viajes_activos(
        self, *, usuario_id: int | None = None, rol: str | None = None
    ) -> list[dict]:
        viajes = await self.repo.viajes_activos()
        return [v for v in viajes if rol != "REPARTIDOR" or v["repartidor_id"] == usuario_id]

    async def repartidores_disponibles(
        self, *, rol: str, autorizado: bool | None = None
    ) -> list[dict]:
        self._personal(rol, autorizado=autorizado)
        return [
            {"id": r.repartidor_id, "nombre": r.nombre, "estado": "DISPONIBLE"}
            for r in await self.repo.repartidores_disponibles()
        ]

    async def corregir_entrega(
        self,
        envio_id: int,
        *,
        motivo: str,
        version_esperada: int,
        regreso_confirmado: bool,
        usuario_id: int,
        rol: str,
        autorizado: bool | None = None,
    ) -> dict:
        if not (rol in {"ADMINISTRADOR", "DUENIO"} if autorizado is None else autorizado):
            raise SinPermiso("Solo administracion puede corregir una entrega")
        if not motivo.strip() or regreso_confirmado is not True:
            raise ReglaDeNegocio("La correccion exige motivo y confirmar el paquete en el local")
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if envio["estado"] != "ENTREGADO" or viaje["estado"] not in {"EN_RUTA", "FINALIZADO"}:
            raise ReglaDeNegocio("Solo se puede corregir una entrega registrada en un viaje real")
        await self.repo.desenganchar_envio(envio_id, motivo.strip())
        await self.pedidos.cambiar_estado(
            envio["pedido_id"],
            EstadoPedido.LISTO,
            usuario_id=usuario_id,
            motivo=motivo,
            version_esperada=version_esperada,
            estado_esperado="ENTREGADO",
            origen="DELIVERY",
            rol=rol,
            correccion=True,
            permitir_correccion=autorizado,
            tratamiento_stock="CONSERVAR",
            permitir_recuperacion=autorizado,
        )
        if viaje["estado"] == "EN_RUTA":
            await self._cerrar_si_resuelto(viaje, usuario_id)
        await auditoria.registrar(
            self.uow,
            accion="ENVIO_ENTREGA_CORREGIDA",
            entidad="envio",
            entidad_id=envio_id,
            usuario_id=usuario_id,
            datos={"motivo": motivo, "regreso_confirmado": True, "envio_anterior": envio},
        )
        return {"envio_id": envio_id, "pedido_id": envio["pedido_id"], "viaje_id": None}

    async def detalle_viaje(
        self, viaje_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        viaje = await self.repo.viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        self._autorizar(viaje, usuario_id, rol)
        return {**viaje, "envios": await self.repo.envios_del_viaje(viaje_id)}

    async def viaje_del_repartidor(
        self, repartidor_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict | None:
        self._autorizar({"repartidor_id": repartidor_id}, usuario_id, rol)
        abierto = await self.repo.viaje_abierto_de(repartidor_id)
        if abierto is None:
            return None
        return await self.detalle_viaje(abierto["id"], usuario_id=usuario_id, rol=rol)
