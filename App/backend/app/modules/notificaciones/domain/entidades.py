"""Entidades del modulo de Notificaciones / Bot de WhatsApp (EDT 1.7).

Cubre el armado del mensaje -que evento dispara que plantilla, con que
variables- sin depender de FastAPI, psycopg, ni del canal de envio real.
El envio efectivo (WhatsApp Cloud API a traves de n8n) es una tarea aparte
del cronograma, a cargo de otro integrante: este modulo deja el puerto
`EnviadorNotificaciones` (ver infrastructure/enviadores.py) para que se
implemente sin tocar el resto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventoNotificacion(StrEnum):
    """Coincide con el CHECK plantilla_clave_chk de la migracion 006."""

    BIENVENIDA = "BIENVENIDA"
    PEDIDO_CONFIRMADO = "PEDIDO_CONFIRMADO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    ALERTA_STOCK = "ALERTA_STOCK"
    CIERRE_CAJA = "CIERRE_CAJA"


#: Eventos ligados a un pedido puntual: sin pedido_id no hay forma de armar
#: el mensaje (necesitan numero de pedido, repartidor, etc.).
EVENTOS_QUE_REQUIEREN_PEDIDO = frozenset(
    {
        EventoNotificacion.PEDIDO_CONFIRMADO,
        EventoNotificacion.EN_CAMINO,
        EventoNotificacion.ENTREGADO,
    }
)


def renderizar_plantilla(cuerpo: str, variables: dict[str, str]) -> str:
    """Reemplaza placeholders `{{variable}}` por su valor.

    Sigue la sintaxis ya usada en App/db/seed.sql (`{{numero_pedido}}`,
    `{{total}}`, `{{repartidor}}`, `{{url_menu}}`). Una variable que la
    plantilla pide pero no llega en `variables` queda a la vista como
    `{{variable}}` en vez de reventar: un mensaje con un hueco visible es
    mejor que no enviar nada, sobre todo con el limite de 30 s del RNF-10.
    """
    resultado = cuerpo
    for clave, valor in variables.items():
        resultado = resultado.replace(f"{{{{{clave}}}}}", valor)
    return resultado


@dataclass(slots=True, frozen=True)
class PlantillaActiva:
    id: int
    clave: str
    nombre: str
    cuerpo: str


@dataclass(slots=True, frozen=True)
class NotificacionPendiente:
    id: int
    destinatario: str
    cuerpo_renderizado: str
    intentos: int


class AccionesAuditoriaBot:
    """Valores de `accion` que este modulo registra en la tabla auditoria."""

    PLANTILLA_REGISTRADA = "PLANTILLA_NOTIFICACION_REGISTRADA"
    PLANTILLA_MODIFICADA = "PLANTILLA_NOTIFICACION_MODIFICADA"
    PLANTILLA_DESACTIVADA = "PLANTILLA_NOTIFICACION_DESACTIVADA"
    SIN_DESTINATARIO = "NOTIFICACION_SIN_DESTINATARIO"
