"""Casos de uso del modulo de asignacion de repartidores (EDT 1.3).

Orquesta el algoritmo del dominio con la base: arma los viajes, los despacha
y registra las entregas, dejando rastro en el historial de estados y en
auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

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

# Valores por defecto si la tabla de parámetros no define la configuración de delivery.
RADIO_AGRUPACION_POR_DEFECTO = 1.5
RADIO_BUSQUEDA_POR_DEFECTO = 10.0


class AccionesDelivery:
    """Nombres de las acciones de delivery que se registran en auditoría."""

    VIAJE_ASIGNADO = "VIAJE_ASIGNADO"
    VIAJE_INICIADO = "VIAJE_INICIADO"
    ENVIO_ENTREGADO = "ENVIO_ENTREGADO"
    VIAJE_FINALIZADO = "VIAJE_FINALIZADO"


@dataclass(slots=True)
class ViajeCreado:
    """Viaje que la planificación automática dejó persistido en la base."""

    viaje_id: int
    repartidor_id: int
    repartidor_nombre: str
    pedidos: list[int]
    distancia_km: float | None


@dataclass(slots=True)
class ResultadoPlanificacion:
    """Resultado de una corrida de planificación automática."""

    viajes: list[ViajeCreado]
    sin_asignar: list[int]
    pedidos_evaluados: int
    repartidores_disponibles: int


class AutoridadPedidos(Protocol):
    """Puerto hacia el módulo de pedidos, dueño de las transiciones de estado del pedido."""

    async def cambiar_estado(self, pedido_id: int, nuevo: EstadoPedido, **opciones) -> dict: ...


class CobrosEnEfectivo(Protocol):
    """Puerto hacia pagos, dueño del registro del dinero, sus reintentos y su auditoría."""

    async def registrar_pago_efectivo(
        self, pedido_id: int, monto_recibido: Decimal, **opciones
    ) -> Any: ...


class ServicioDelivery:
    """Casos de uso de reparto: planificación, salida, entregas, cobros, fallos y correcciones."""

    def __init__(
        self,
        uow: UnidadDeTrabajo,
        repositorio: RepositorioDeliverySQL,
        pedidos: AutoridadPedidos,
        cobros: CobrosEnEfectivo | None = None,
    ) -> None:
        """Recibe la unidad de trabajo, el repositorio SQL, la autoridad de pedidos y el registro
        de cobros en efectivo que usa el repartidor al entregar.
        """
        self.uow = uow
        self.repo = repositorio
        self.pedidos = pedidos
        self.cobros = cobros

    # ------------------------------ planificacion ---------------------

    async def _parametros(self) -> tuple[float, float, None]:
        """Lee radios de cercanía; la cantidad asignada no tiene un máximo."""
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
        return radio_agrupacion, radio_busqueda, None

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
        # Bloquea pedidos y repartidores para que dos planificaciones simultáneas no se pisen.
        repartidores = await self.repo.repartidores_disponibles(bloquear=True)
        candidatos = await self.repo.pedidos_para_despachar(bloquear=True)
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
        disponibles = len({p.repartidor.repartidor_id for p in propuestas if p.repartidor})

        # Persiste cada propuesta asignable: viaje, envíos ordenados, repartidor en ruta y
        # auditoría.
        for propuesta in propuestas:
            if not propuesta.asignable:
                sin_asignar.extend(p.pedido_id for p in propuesta.grupo.pedidos)
                continue

            repartidor = propuesta.repartidor
            assert repartidor is not None

            viaje_id = await self._viaje_para_asignacion(
                repartidor.repartidor_id, usuario_id, automatica=True
            )
            siguiente_orden = await self.repo.siguiente_orden(viaje_id)

            # El primer envío guarda la distancia desde el repartidor; el resto no la tiene.
            for orden, pedido in enumerate(propuesta.grupo.pedidos, start=siguiente_orden):
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

            anterior = next((v for v in viajes if v.viaje_id == viaje_id), None)
            if anterior is not None:
                anterior.pedidos.extend(pedidos_ids)
                continue
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

    async def _viaje_para_asignacion(
        self, repartidor_id: int, usuario_id: int | None, *, automatica: bool
    ) -> int:
        """Acumula en la próxima salida sin anexar pedidos a una salida ya iniciada."""
        planificado = await self.repo.viaje_planificado_de(repartidor_id)
        if planificado is not None:
            return planificado
        return await self.repo.crear_viaje(
            repartidor_id, asignado_por=usuario_id, automatica=automatica
        )

    # ------------------------------ operacion -------------------------

    @staticmethod
    def _personal(rol: str | None, *, autorizado: bool | None = None) -> None:
        """Exige que la operación la haga personal del local (o un permiso explícito)."""
        permitido = rol is None or rol in {"EMPLEADO", "ADMINISTRADOR", "DUENIO"}
        if not (permitido if autorizado is None else autorizado):
            raise SinPermiso("Esta operacion requiere personal del local")

    @staticmethod
    def _autorizar(viaje: dict, usuario_id: int | None, rol: str | None) -> None:
        """Valida que el usuario pueda operar el viaje: un repartidor solo el propio."""
        if rol == "REPARTIDOR" and viaje["repartidor_id"] != usuario_id:
            raise SinPermiso("Solo podes operar tu propio viaje")
        if rol is not None and rol not in {"REPARTIDOR", "EMPLEADO", "ADMINISTRADOR", "DUENIO"}:
            raise SinPermiso("No tenes acceso al reparto")

    async def iniciar_viaje(
        self, viaje_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        """Registra la salida del repartidor y pasa sus pedidos a "en camino".

        Solo aplica a viajes planificados sin salida y cuyos envíos sean deliveries listos y
        asignados.
        """
        viaje = await self.repo.bloquear_viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        self._autorizar(viaje, usuario_id, rol)
        if viaje["estado"] != "PLANIFICADO" or viaje["salida_en"] is not None:
            raise ReglaDeNegocio("Solo se puede iniciar un viaje planificado sin salida")
        envios = await self.repo.envios_del_viaje(viaje_id)
        if not envios:
            raise ReglaDeNegocio("El viaje no tiene envios asignados")
        # Verifica que todos los pedidos del viaje sigan siendo deliveries listos antes de salir.
        for envio in envios:
            pedido = await self.repo.pedido_asignable(envio["pedido_id"])
            if (
                envio["estado"] != "ASIGNADO"
                or pedido["estado"] != "LISTO"
                or pedido["tipo_entrega"] != "DELIVERY"
            ):
                raise ReglaDeNegocio("Todos los pedidos deben ser delivery listo y asignado")
        # Marca viaje y envíos en ruta y delega en pedidos el cambio de estado de cada uno.
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
        """Obtiene un envío y bloquea su viaje para operar sin carreras.

        Relee el envío tras el bloqueo para detectar si otra operación lo cambió de viaje.
        """
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

    async def cobrar_en_efectivo(
        self,
        envio_id: int,
        *,
        monto: Decimal,
        clave_operacion: str,
        usuario_id: int | None = None,
        rol: str | None = None,
        ip_cliente: str | None = None,
    ) -> dict:
        """Registra el efectivo que el repartidor recibió del cliente en la puerta.

        Solo en el propio viaje y con el envío en camino, igual que la entrega. El cobro queda
        conciliado a nombre del repartidor, así la entrega se puede cerrar sin llamar al local;
        el arqueo de caja lo incluye como efectivo recibido. Pagos valida que ``monto`` no supere
        el saldo y resuelve los reintentos de la misma ``clave_operacion`` sin duplicar el cobro.
        """
        if self.cobros is None:
            raise ReglaDeNegocio("El cobro en efectivo no está disponible en reparto")
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if (
            envio["estado"] != "EN_CAMINO"
            or viaje["estado"] != "EN_RUTA"
            or viaje["salida_en"] is None
        ):
            raise ReglaDeNegocio("Solo se cobra un envío en camino durante el viaje")
        resultado = await self.cobros.registrar_pago_efectivo(
            pedido_id=envio["pedido_id"],
            monto_recibido=monto,
            monto_a_pagar=monto,
            conciliar_inmediato=True,
            registrado_por=usuario_id,
            ip_cliente=ip_cliente,
            clave_operacion=clave_operacion,
        )
        return {
            "envio_id": envio_id,
            "pedido_id": envio["pedido_id"],
            "monto_cobrado": resultado.detalle.monto_cobrado,
            "saldo_restante": resultado.detalle.saldo_restante,
        }

    async def registrar_entrega(
        self, envio_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict:
        """Confirma la entrega de un envío en camino y cierra el viaje si era el último."""
        envio, viaje = await self._envio_bloqueado(envio_id, usuario_id, rol)
        if (
            envio["estado"] != "EN_CAMINO"
            or viaje["estado"] != "EN_RUTA"
            or viaje["salida_en"] is None
        ):
            raise ReglaDeNegocio("La entrega requiere un envio en camino y salida real del viaje")
        if not await self.repo.pedido_pago_completo(envio["pedido_id"]):
            raise ReglaDeNegocio("La entrega requiere pago completo registrado y conciliado")
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
        """Cierra el viaje y libera al repartidor si todos los envíos quedaron entregados.

        Devuelve ``True`` si el viaje se cerró. Sin salida real el viaje se considera cancelado.
        """
        # Un fallo sigue ocupando al repartidor hasta confirmar el regreso al local.
        envios = await self.repo.envios_del_viaje(viaje["id"])
        if any(e["estado"] != "ENTREGADO" for e in envios):
            return False
        estado = "FINALIZADO" if viaje["salida_en"] else "CANCELADO"
        await self.repo.cambiar_estado_viaje(viaje["id"], estado)
        ocupado = await self.repo.tiene_viajes_abiertos(viaje["repartidor_id"])
        await self.repo.cambiar_estado_repartidor(
            viaje["repartidor_id"], "EN_RUTA" if ocupado else "DISPONIBLE"
        )
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
        """Saca un envío de su viaje antes de que el repartidor salga del local."""
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
        """Asigna manualmente un delivery listo a un repartidor disponible.

        Si el pedido tenía un envío entregado en un viaje finalizado (entrega corregida), se
        recupera ese envío y se lo desengancha antes de crear el viaje nuevo.
        """
        self._personal(rol, autorizado=autorizado)
        self._autorizar({"repartidor_id": repartidor_id}, usuario_id, rol)
        if not motivo.strip():
            raise ReglaDeNegocio("La asignacion requiere un motivo")
        disponibles = await self.repo.repartidores_disponibles(
            bloquear=True, repartidor_id=repartidor_id
        )
        if not any(r.repartidor_id == repartidor_id for r in disponibles):
            raise ReglaDeNegocio("El repartidor no esta disponible")
        pedido = await self.repo.pedido_asignable(pedido_id)
        if pedido is None:
            raise NoEncontrado("El pedido no existe")
        if pedido["estado"] != "LISTO" or pedido["tipo_entrega"] != "DELIVERY":
            raise ReglaDeNegocio("Solo se puede asignar un delivery listo")
        # Un envío entregado en un viaje ya finalizado se puede recuperar para un nuevo intento.
        existente = await self.repo.envio_del_pedido(pedido_id)
        recuperado = bool(
            existente
            and existente["estado"] == "ENTREGADO"
            and existente["estado_viaje"] == "FINALIZADO"
        )
        if existente and existente["viaje_id"] is not None and not recuperado:
            raise ReglaDeNegocio("Desasigna el envio antes de volver a asignarlo")
        # Recuperación: se audita el envío anterior y se lo libera del viaje viejo.
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
        # Anexa a la próxima salida o crea otra si el repartidor ya salió.
        viaje_id = await self._viaje_para_asignacion(
            repartidor_id, usuario_id, automatica=False
        )
        envio_id = await self.repo.asignar_envio(
            pedido_id=pedido_id,
            viaje_id=viaje_id,
            zona_id=pedido["zona_id"],
            orden=await self.repo.siguiente_orden(viaje_id),
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
        """Desasigna el envío y lo asigna a otro repartidor (desasignar + asignar)."""
        self._personal(rol, autorizado=autorizado)
        previo = await self.repo.envio(envio_id)
        if previo is None:
            raise NoEncontrado("El envio no existe")
        ids = {repartidor_id}
        if previo["repartidor_id"] is not None:
            ids.add(previo["repartidor_id"])
        await self.repo.bloquear_repartidores(sorted(ids))
        actual = await self.repo.envio(envio_id)
        if actual["viaje_id"] != previo["viaje_id"]:
            raise ReglaDeNegocio("La asignacion cambio; actualiza el viaje")
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
        """Marca como fallido un envío en camino; el repartidor sigue ocupado."""
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
        """Confirma que el envío fallido volvió al local y devuelve el pedido a LISTO.

        El cambio de estado se hace como corrección, controlando la versión del pedido.
        """
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
        """Lista viajes abiertos; a un repartidor solo le muestra los suyos."""
        viajes = await self.repo.viajes_activos()
        return [v for v in viajes if rol != "REPARTIDOR" or v["repartidor_id"] == usuario_id]

    async def repartidores_disponibles(
        self, *, rol: str, autorizado: bool | None = None
    ) -> list[dict]:
        """Repartidores activos y su carga para asignación manual."""
        self._personal(rol, autorizado=autorizado)
        return [
            {"id": r.repartidor_id, "nombre": r.nombre, "estado": r.estado,
             "hamburguesas_asignadas": r.hamburguesas_asignadas}
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
        """Revierte una entrega registrada: el paquete volvió y el pedido vuelve a LISTO.

        Solo administración. El stock ya descontado se conserva y el pedido puede volver a
        asignarse.
        """
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
        # Si el viaje seguía en ruta, puede quedar resuelto tras sacar este envío.
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
        """Devuelve el viaje con sus envíos, validando el acceso del usuario."""
        viaje = await self.repo.viaje(viaje_id)
        if viaje is None:
            raise NoEncontrado("El viaje no existe")
        self._autorizar(viaje, usuario_id, rol)
        return {**viaje, "envios": await self.repo.envios_del_viaje(viaje_id)}

    async def viaje_del_repartidor(
        self, repartidor_id: int, *, usuario_id: int | None = None, rol: str | None = None
    ) -> dict | None:
        """Devuelve el viaje abierto del repartidor, o ``None`` si no tiene."""
        self._autorizar({"repartidor_id": repartidor_id}, usuario_id, rol)
        abierto = await self.repo.viaje_abierto_de(repartidor_id)
        if abierto is None:
            return None
        return await self.detalle_viaje(abierto["id"], usuario_id=usuario_id, rol=rol)
