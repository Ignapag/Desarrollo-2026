"""Contadores de intentos de login en la tabla intento_login (migración 032).

Cada reserva es una única sentencia ``INSERT ... ON CONFLICT DO UPDATE ... WHERE``:
PostgreSQL bloquea la fila de la clave y reevalúa el umbral sobre la versión
confirmada, así que intentos concurrentes nunca superan el máximo. El username
se normaliza con ``lower`` igual que la columna CITEXT ``usuario.username``.
"""

from __future__ import annotations

from app.core.db import UnidadDeTrabajo

_PURGA_POR_RESERVA = 100

_RESERVAR = """
    INSERT INTO intento_login AS t (clave, fallos, vence_en)
    VALUES ({clave}, 1, now() + make_interval(secs => %s))
    ON CONFLICT (clave) DO UPDATE
    SET fallos = CASE WHEN t.vence_en <= now() THEN 1 ELSE t.fallos + 1 END,
        vence_en = CASE WHEN t.vence_en <= now() THEN EXCLUDED.vence_en ELSE t.vence_en END
    WHERE t.vence_en <= now() OR t.fallos < %s
    RETURNING fallos
"""
_CLAVE_USUARIO = "'usuario:' || lower(%s::text)"
_CLAVE_ORIGEN = "'ip:' || %s::text"


class RepositorioIntentosLoginSQL:
    """Implementa ``RegistroIntentosLogin`` sobre la unidad de trabajo recibida."""

    def __init__(self, uow: UnidadDeTrabajo) -> None:
        """Recibe la unidad de trabajo cuya transacción confirma los contadores."""
        self.uow = uow

    async def _reservar(self, clave: str, valor: str, maximo: int, ventana_segundos: int) -> bool:
        fila = await self.uow.uno(
            _RESERVAR.format(clave=clave), (valor, ventana_segundos, maximo)
        )
        return fila is not None

    async def reservar_usuario(self, username: str, maximo: int, ventana_segundos: int) -> bool:
        """Suma un fallo provisorio al username; ``False`` si ya alcanzó el máximo."""
        return await self._reservar(_CLAVE_USUARIO, username, maximo, ventana_segundos)

    async def reservar_origen(self, origen: str, maximo: int, ventana_segundos: int) -> bool:
        """Suma un fallo provisorio al origen; ``False`` si ya alcanzó el máximo."""
        return await self._reservar(_CLAVE_ORIGEN, origen, maximo, ventana_segundos)

    async def purgar_vencidos(self) -> None:
        """Borra un lote de ventanas vencidas sin esperar filas bloqueadas por otro login."""
        await self.uow.ejecutar(
            """
            DELETE FROM intento_login WHERE clave IN (
                SELECT clave FROM intento_login WHERE vence_en < now()
                ORDER BY vence_en LIMIT %s FOR UPDATE SKIP LOCKED
            )
            """,
            (_PURGA_POR_RESERVA,),
        )

    async def reiniciar_usuario(self, username: str) -> None:
        """Elimina el contador del username después de un login exitoso."""
        await self.uow.ejecutar(
            f"DELETE FROM intento_login WHERE clave = {_CLAVE_USUARIO}", (username,)
        )

    async def devolver_origen(self, origen: str) -> None:
        """Descuenta el cupo provisorio de un login exitoso: el origen solo cuenta fallos."""
        await self.uow.ejecutar(
            f"""
            UPDATE intento_login SET fallos = fallos - 1
            WHERE clave = {_CLAVE_ORIGEN} AND fallos > 0 AND vence_en > now()
            """,
            (origen,),
        )
