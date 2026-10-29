"""Caso de uso que limita los intentos de inicio de sesión por username y origen.

Se ejecuta en una transacción corta propia, antes de la del login: el cupo
queda confirmado aunque el login responda 401 y un intento rechazado no llega
a buscar la cuenta ni a ejecutar bcrypt.
"""

from __future__ import annotations

from typing import Protocol

from app.errores import DemasiadosIntentos
from app.modules.usuarios.domain.limite_login import (
    MENSAJE_DEMASIADOS_INTENTOS,
    IntentoReservado,
    PoliticaIntentosLogin,
)


class RegistroIntentosLogin(Protocol):
    """Puerto de persistencia de los contadores que implementa el repositorio SQL."""

    async def reservar_usuario(self, username: str, maximo: int, ventana_segundos: int) -> bool: ...
    async def reservar_origen(self, origen: str, maximo: int, ventana_segundos: int) -> bool: ...
    async def purgar_vencidos(self) -> None: ...
    async def reiniciar_usuario(self, username: str) -> None: ...
    async def devolver_origen(self, origen: str) -> None: ...


class ServicioLimiteLogin:
    """Reserva un cupo por intento y lo libera cuando el login es exitoso."""

    def __init__(self, registro: RegistroIntentosLogin, politica: PoliticaIntentosLogin) -> None:
        """Recibe el registro de contadores y los umbrales vigentes."""
        self.registro = registro
        self.politica = politica

    async def reservar(self, username: str, origen: str | None) -> IntentoReservado:
        """Consume un cupo del username y del origen, o lanza ``DemasiadosIntentos``.

        El mensaje es el mismo para ambos límites y para cuentas inexistentes:
        no revela si el usuario existe ni cuánto falta. Si el origen está
        bloqueado, quien llama debe revertir la reserva del username.
        """
        ventana = self.politica.ventana_segundos
        if not await self.registro.reservar_usuario(
            username, self.politica.max_fallos_usuario, ventana
        ):
            raise DemasiadosIntentos(MENSAJE_DEMASIADOS_INTENTOS)
        if origen is not None and not await self.registro.reservar_origen(
            origen, self.politica.max_fallos_origen, ventana
        ):
            raise DemasiadosIntentos(MENSAJE_DEMASIADOS_INTENTOS)
        await self.registro.purgar_vencidos()
        return IntentoReservado(username=username, origen=origen)

    async def confirmar_exito(self, intento: IntentoReservado) -> None:
        """Reinicia el contador del username y devuelve el cupo que usó el origen."""
        await self.registro.reiniciar_usuario(intento.username)
        if intento.origen is not None:
            await self.registro.devolver_origen(intento.origen)
