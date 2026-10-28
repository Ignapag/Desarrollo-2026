"""Administración de permisos: solo el administrador puede consultar y guardar."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.modules.usuarios.presentation.dependencias import ServicioAccesoDep, SoloAdministrador

router = APIRouter(prefix="/api/acceso", tags=["Control de acceso"])


class PermisosEntrada(BaseModel):
    """Nueva lista de permisos de un rol con la versión que se editó."""

    model_config = ConfigDict(extra="forbid")
    permisos: list[str] = Field(max_length=100)
    version: int = Field(ge=1, strict=True)


@router.get("")
async def consultar(_admin: SoloAdministrador, servicio: ServicioAccesoDep):
    """Devuelve el catálogo de módulos y la matriz de permisos por rol."""
    return await servicio.consultar()


@router.put("/roles/{rol}")
async def guardar(rol: str, datos: PermisosEntrada,
                  admin: SoloAdministrador, servicio: ServicioAccesoDep):
    """Reemplaza los permisos de un rol, controlando que nadie los haya cambiado."""
    return await servicio.guardar(rol, datos.permisos, datos.version, admin.usuario_id)
