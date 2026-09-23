"""Esquemas Pydantic del modulo de Usuarios y Seguridad."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.usuarios.application.servicio_usuarios import DatosNuevoUsuario, DatosUsuario


class LoginEntrada(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SesionSalida(BaseModel):
    """Lo que ve el frontend al iniciar sesion o al pedir 'quien soy'.

    Nunca incluye el token: viaja solo en la cookie HttpOnly, no en el
    cuerpo de la respuesta.
    """

    id: int
    nombre: str
    apellido: str
    username: str
    rol: str


class UsuarioSalida(BaseModel):
    id: int
    nombre: str
    apellido: str
    username: str
    email: str | None
    telefono: str | None
    rol: str
    estado: str
    fecha_alta: datetime
    actualizado_en: datetime
    ultimo_acceso: datetime | None


class NuevoUsuarioEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    apellido: str = Field(min_length=1)
    username: str = Field(min_length=4)
    password: str = Field(min_length=8)
    rol: str
    email: str | None = None
    telefono: str | None = None

    def a_datos(self) -> DatosNuevoUsuario:
        return DatosNuevoUsuario(
            nombre=self.nombre,
            apellido=self.apellido,
            username=self.username,
            password=self.password,
            rol=self.rol,
            email=self.email,
            telefono=self.telefono,
        )


class ModificarUsuarioEntrada(BaseModel):
    nombre: str = Field(min_length=1)
    apellido: str = Field(min_length=1)
    username: str = Field(min_length=4)
    estado: str

    def a_datos(self) -> DatosUsuario:
        return DatosUsuario(
            nombre=self.nombre,
            apellido=self.apellido,
            username=self.username,
            estado=self.estado,
        )


class AsignarRolEntrada(BaseModel):
    rol: str


class EventoAuditoriaSalida(BaseModel):
    id: int
    usuario_id: int | None
    username: str | None
    accion: str
    entidad: str
    entidad_id: str | None
    datos: Any | None
    ip: str | None
    creado_en: datetime
