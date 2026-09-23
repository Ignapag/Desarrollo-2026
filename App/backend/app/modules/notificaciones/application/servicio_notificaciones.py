"""Casos de uso del modulo de Notificaciones (EDT 1.7).

Dos responsabilidades separadas:

1. Encolar (`notificar`): arma el mensaje a partir de la plantilla activa
   del evento y lo deja en estado PENDIENTE. La llaman los modulos que
   disparan un aviso -Pedidos al confirmar, Delivery al cambiar el estado
   de un envio- pasando las variables que su plantilla necesita (ver
   App/db/seed.sql para los nombres ya usados: numero_pedido, total,
   repartidor, url_menu).
2. Procesar (`procesar_pendientes`): intenta el envio efectivo a traves del
   puerto `EnviadorNotificaciones` y actualiza el estado. Hoy corre bajo
   demanda desde un endpoint; cuando se integre n8n puede dispararse desde
   un webhook o un job en su lugar, sin cambiar esta clase.

La gestion de plantillas (CU_BOT_04 a CU_BOT_07) vive en la misma clase por
simplicidad: son operaciones chicas de mantenimiento, no un caso de uso con
flujo propio.
"""

from __future__ import annotations

from app.core import auditoria
from app.core.db import UnidadDeTrabajo
from app.core.errores import NoEncontrado, ReglaDeNegocio
from app.modules.notificaciones.domain.entidades import (
    EVENTOS_QUE_REQUIEREN_PEDIDO,
    AccionesAuditoriaBot,
    EventoNotificacion,
    renderizar_plantilla,
)
from app.modules.notificaciones.infrastructure.enviadores import EnviadorNotificaciones
from app.modules.notificaciones.infrastructure.repositorio_sql import RepositorioNotificacionesSQL

EVENTOS_VALIDOS = {evento.value for evento in EventoNotificacion}


class ServicioNotificaciones:
    def __init__(
        self,
        uow: UnidadDeTrabajo,
        repositorio: RepositorioNotificacionesSQL,
        enviador: EnviadorNotificaciones,
    ) -> None:
        self.uow = uow
        self.repo = repositorio
        self.enviador = enviador

    # ------------------------------ encolado (CU_BOT_01/02/03) ---------

    async def notificar(
        self,
        evento: EventoNotificacion,
        *,
        destinatario: str,
        variables: dict[str, str] | None = None,
        cliente_id: int | None = None,
        pedido_id: int | None = None,
    ) -> int | None:
        """Arma y encola una notificacion.

        Devuelve el id de la notificacion creada, o None si no hay
        plantilla activa para el evento o no hay destinatario: se registra
        la incidencia en auditoria en vez de fallar el flujo que la
        dispara (un pedido se confirma igual aunque el aviso no pueda
        armarse).
        """
        if evento in EVENTOS_QUE_REQUIEREN_PEDIDO and pedido_id is None:
            raise ReglaDeNegocio(f"El evento {evento.value} requiere un pedido_id")

        if not destinatario:
            await auditoria.registrar(
                self.uow,
                accion=AccionesAuditoriaBot.SIN_DESTINATARIO,
                entidad="notificacion",
                datos={"evento": evento.value, "pedido_id": pedido_id},
            )
            return None

        plantilla = await self.repo.plantilla_activa(evento.value)
        if plantilla is None:
            return None

        cuerpo = renderizar_plantilla(plantilla.cuerpo, variables or {})
        return await self.repo.crear(
            plantilla_id=plantilla.id,
            clave=evento.value,
            destinatario=destinatario,
            cliente_id=cliente_id,
            pedido_id=pedido_id,
            cuerpo_renderizado=cuerpo,
        )

    # ------------------------------ envio efectivo ----------------------

    async def procesar_pendientes(self, *, limite: int = 20) -> dict[str, int]:
        """Intenta enviar las notificaciones PENDIENTE mas antiguas.

        El envio real (WhatsApp Cloud API / n8n) lo hace `self.enviador`;
        esta clase solo orquesta el estado. Ver infrastructure/enviadores.py.
        """
        pendientes = await self.repo.pendientes(limite=limite)
        enviadas = fallidas = 0

        for notificacion in pendientes:
            try:
                await self.enviador.enviar(
                    notificacion.destinatario, notificacion.cuerpo_renderizado
                )
            except Exception as exc:  # noqa: BLE001 - cualquier falla del canal es FALLIDA
                await self.repo.marcar_fallida(notificacion.id, error=str(exc))
                fallidas += 1
                continue
            await self.repo.marcar_enviada(notificacion.id)
            enviadas += 1

        return {"procesadas": len(pendientes), "enviadas": enviadas, "fallidas": fallidas}

    # ------------------------------ plantillas (CU_BOT_04 a 07) ---------

    async def buscar_plantillas(
        self, *, nombre: str | None = None, evento: str | None = None, activa: bool | None = None
    ) -> list[dict]:
        return await self.repo.buscar_plantillas(nombre=nombre, evento=evento, activa=activa)

    async def registrar_plantilla(
        self, *, clave: str, nombre: str, cuerpo: str, activa: bool, ejecutor_id: int | None
    ) -> dict:
        if clave not in EVENTOS_VALIDOS:
            raise ReglaDeNegocio(f"Evento invalido: {clave}")

        plantilla_id = await self.repo.crear_plantilla(
            clave=clave, nombre=nombre, cuerpo=cuerpo, activa=activa, actualizado_por=ejecutor_id
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoriaBot.PLANTILLA_REGISTRADA,
            entidad="notificacion_plantilla",
            entidad_id=plantilla_id,
            usuario_id=ejecutor_id,
            datos={"clave": clave},
        )
        return await self._obtener_plantilla(plantilla_id)

    async def modificar_plantilla(
        self, plantilla_id: int, *, nombre: str, cuerpo: str, activa: bool, ejecutor_id: int | None
    ) -> dict:
        await self._obtener_plantilla(plantilla_id)
        await self.repo.actualizar_plantilla(
            plantilla_id, nombre=nombre, cuerpo=cuerpo, activa=activa, actualizado_por=ejecutor_id
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoriaBot.PLANTILLA_MODIFICADA,
            entidad="notificacion_plantilla",
            entidad_id=plantilla_id,
            usuario_id=ejecutor_id,
        )
        return await self._obtener_plantilla(plantilla_id)

    async def desactivar_plantilla(self, plantilla_id: int, *, ejecutor_id: int | None) -> dict:
        actual = await self._obtener_plantilla(plantilla_id)
        if not actual["activa"]:
            raise ReglaDeNegocio("La plantilla ya esta inactiva")

        await self.repo.cambiar_estado_plantilla(
            plantilla_id, activa=False, actualizado_por=ejecutor_id
        )
        await auditoria.registrar(
            self.uow,
            accion=AccionesAuditoriaBot.PLANTILLA_DESACTIVADA,
            entidad="notificacion_plantilla",
            entidad_id=plantilla_id,
            usuario_id=ejecutor_id,
        )
        return await self._obtener_plantilla(plantilla_id)

    async def _obtener_plantilla(self, plantilla_id: int) -> dict:
        plantilla = await self.repo.obtener_plantilla(plantilla_id)
        if plantilla is None:
            raise NoEncontrado("La plantilla no existe")
        return plantilla

    # ------------------------------ consulta de envios -------------------

    async def listar(
        self, *, pedido_id: int | None = None, estado: str | None = None, limite: int = 100
    ) -> list[dict]:
        return await self.repo.listar(pedido_id=pedido_id, estado=estado, limite=limite)
