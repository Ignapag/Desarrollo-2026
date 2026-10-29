"""Política de limitación de intentos de inicio de sesión (CU_USR_01).

Lógica pura: define cuántos fallos se toleran por username y por origen y en
qué ventana. Cada intento consume un cupo antes de verificar la contraseña;
así, muchos intentos simultáneos nunca evalúan más contraseñas que el umbral.
"""

from __future__ import annotations

from dataclasses import dataclass

MENSAJE_DEMASIADOS_INTENTOS = (
    "Demasiados intentos de inicio de sesión. Esperá unos minutos y volvé a intentar."
)


@dataclass(slots=True, frozen=True)
class PoliticaIntentosLogin:
    """Umbrales de fallos por username y por origen dentro de una ventana fija.

    La ventana empieza con el primer fallo y, alcanzado el umbral, el login se
    rechaza hasta que vence, aunque la contraseña sea correcta.
    """

    max_fallos_usuario: int
    max_fallos_origen: int
    ventana_segundos: int

    def __post_init__(self) -> None:
        """Rechaza umbrales o ventanas que desactivarían el límite por error."""
        if self.max_fallos_usuario < 1 or self.max_fallos_origen < 1:
            raise ValueError("Los umbrales de intentos de login deben ser positivos")
        if self.ventana_segundos < 1:
            raise ValueError("La ventana de intentos de login debe ser positiva")


@dataclass(slots=True, frozen=True)
class IntentoReservado:
    """Cupo consumido por un intento en curso; ``origen`` es ``None`` sin IP confiable."""

    username: str
    origen: str | None
