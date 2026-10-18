"""Identidad de una operación financiera y validación de sus reintentos."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.errores import DatosInvalidos, ReglaDeNegocio
from app.modules.pagos.domain.entidades import Pago


class OperacionesFinancieras(Protocol):
    async def bloquear_operacion(self, clave: str) -> None: ...

    async def obtener_operacion(self, clave: str) -> tuple[Pago, dict] | None: ...


def solicitud_operacion(**valores) -> dict:
    return {
        clave: format(valor, ".2f") if isinstance(valor, Decimal) else valor
        for clave, valor in valores.items()
    }


async def recuperar_operacion(
    repo: OperacionesFinancieras,
    clave: str | None,
    solicitud: dict,
) -> tuple[Pago, dict] | None:
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
