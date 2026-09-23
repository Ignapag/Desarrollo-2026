"""Puerto de envio de notificaciones y su implementacion de desarrollo.

`EnviadorNotificaciones` es la unica interfaz que `ServicioNotificaciones`
necesita: un metodo, `enviar(destinatario, cuerpo)`. Quien integre WhatsApp
Cloud API a traves de n8n (tarea de integracion del EDT 1.7, fuera del
alcance de este modulo) implementa la misma interfaz -por ejemplo,
`EnviadorN8N`- y la conecta en `app/core/dependencias.py`, en el lugar de
`EnviadorSimulado`. El resto del modulo (encolado, plantillas, endpoints,
pruebas) no cambia una linea.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("monuburger.notificaciones")


class EnviadorNotificaciones(Protocol):
    async def enviar(self, destinatario: str, cuerpo: str) -> None:
        """Envia el mensaje. Debe lanzar una excepcion si el envio falla:
        el servicio la interpreta como notificacion FALLIDA y no relanza."""
        ...


class EnviadorSimulado:
    """Adaptador de desarrollo: no llama a ningun servicio externo.

    Deja rastro en el log de la aplicacion. Sirve para probar el encolado y
    el cambio de estado de punta a punta sin depender de WhatsApp Cloud API
    ni de que n8n este levantado.
    """

    async def enviar(self, destinatario: str, cuerpo: str) -> None:
        log.info("Notificacion simulada -> %s: %s", destinatario, cuerpo)
