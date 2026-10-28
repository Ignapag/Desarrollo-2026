"""Identidad de una operación financiera y validación de sus reintentos."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.domain.entidades import Pago


class OperacionesFinancieras(Protocol):
    """Puerto mínimo para la idempotencia de operaciones financieras por clave."""

    async def bloquear_operacion(self, clave: str) -> None: ...

    async def obtener_operacion(self, clave: str) -> tuple[Pago, dict] | None: ...


def solicitud_operacion(**valores) -> dict:
    """Normaliza los datos de una solicitud para compararla en reintentos.

    Los Decimal se formatean con dos decimales para que la comparación no dependa de su
    representación.
    """
    return {
        clave: format(valor, ".2f") if isinstance(valor, Decimal) else valor
        for clave, valor in valores.items()
    }


async def recuperar_operacion(
    repo: OperacionesFinancieras,
    clave: str | None,
    solicitud: dict,
) -> tuple[Pago, dict] | None:
    """Recupera el resultado de una operación ya ejecutada con la misma clave.

    Valida que la clave sea un UUID, bloquea la clave para serializar reintentos concurrentes y
    exige que el reintento traiga exactamente los mismos datos. Devuelve ``None`` si no hay clave o
    si la operación es nueva.
    """
    if clave is None:
        return None
    try:
        clave = str(UUID(str(clave)))
    except ValueError as exc:
        raise DatosInvalidos("La clave de operación debe ser un UUID") from exc
    await repo.bloquear_operacion(clave)
    existente = await repo.obtener_operacion(clave)
    if existente and existente[1].get("solicitud") != solicitud:
        raise ReglaDeNegocio("La clave de operación ya fue utilizada con otros datos")
    return existente
