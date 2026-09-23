"""Endpoints de autenticacion, cuentas y auditoria (EDT 1.8).

Reune tres casos de uso relacionados pero con autorizacion distinta:
  - /api/auth/*        cualquiera con credenciales validas (CU_USR_01)
  - /api/usuarios/*     solo Administrador (CU_USR_02 a CU_USR_06)
  - /api/auditoria      Administrador y Dueno/Supervisor (CU_USR_07)

Sigue la convencion del resto del backend: la dependencia de rol se declara
ANTES que UoW/el servicio en la firma, asi un pedido sin sesion valida se
rechaza sin gastar una conexion a la base (ver docs/GUIA_EQUIPO.md, seccion 7).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Response

from app.core import auditoria
from app.core.config import settings
from app.core.dependencias import (
    AdministradorODuenio,
    IpCliente,
    ServicioAuthDep,
    ServicioUsuariosDep,
    Sesion,
    SoloAdministrador,
    UoW,
)
from app.core.errores import NoEncontrado
from app.modules.usuarios.application.servicio_usuarios import FiltrosUsuario
from app.modules.usuarios.presentation.esquemas import (
    AsignarRolEntrada,
    EventoAuditoriaSalida,
    LoginEntrada,
    ModificarUsuarioEntrada,
    NuevoUsuarioEntrada,
    SesionSalida,
    UsuarioSalida,
)

router = APIRouter(tags=["usuarios"])


# ------------------------------ CU_USR_01: autenticacion -------------------

@router.post("/api/auth/login", response_model=SesionSalida)
async def iniciar_sesion(
    datos: LoginEntrada, respuesta: Response, ip: IpCliente, servicio: ServicioAuthDep
) -> SesionSalida:
    sesion = await servicio.iniciar_sesion(username=datos.username, password=datos.password, ip=ip)
    respuesta.set_cookie(
        key=settings.cookie_sesion,
        value=sesion.token,
        httponly=True,
        secure=settings.es_produccion,
        samesite="lax",
        max_age=settings.jwt_exp_minutos * 60,
    )
    return SesionSalida(
        id=sesion.usuario_id,
        nombre=sesion.nombre,
        apellido=sesion.apellido,
        username=sesion.username,
        rol=sesion.rol.value,
    )


@router.post("/api/auth/logout")
async def cerrar_sesion(respuesta: Response) -> dict:
    respuesta.delete_cookie(settings.cookie_sesion)
    return {"cerrada": True}


@router.get("/api/auth/me", response_model=SesionSalida)
async def quien_soy(sesion: Sesion, servicio: ServicioUsuariosDep) -> SesionSalida:
    usuario = await servicio.obtener(sesion.usuario_id)
    return SesionSalida(
        id=usuario["id"],
        nombre=usuario["nombre"],
        apellido=usuario["apellido"],
        username=usuario["username"],
        rol=usuario["rol"],
    )


# ------------------------------ CU_USR_02 a 06: cuentas ---------------------

@router.get("/api/usuarios", response_model=list[UsuarioSalida])
async def buscar_usuarios(
    _admin: SoloAdministrador,
    servicio: ServicioUsuariosDep,
    nombre: str | None = None,
    apellido: str | None = None,
    username: str | None = None,
    rol: str | None = None,
    estado: str | None = None,
) -> list[UsuarioSalida]:
    filtros = FiltrosUsuario(
        nombre=nombre, apellido=apellido, username=username, rol=rol, estado=estado
    )
    return [UsuarioSalida(**f) for f in await servicio.buscar(filtros)]


@router.get("/api/usuarios/{usuario_id}", response_model=UsuarioSalida)
async def obtener_usuario(
    usuario_id: int, _admin: SoloAdministrador, servicio: ServicioUsuariosDep
) -> UsuarioSalida:
    return UsuarioSalida(**await servicio.obtener(usuario_id))


@router.post("/api/usuarios", response_model=UsuarioSalida, status_code=201)
async def registrar_usuario(
    datos: NuevoUsuarioEntrada, admin: SoloAdministrador, servicio: ServicioUsuariosDep
) -> UsuarioSalida:
    creado = await servicio.registrar(datos.a_datos(), ejecutor_id=admin.usuario_id)
    return UsuarioSalida(**creado)


@router.patch("/api/usuarios/{usuario_id}", response_model=UsuarioSalida)
async def modificar_usuario(
    usuario_id: int,
    datos: ModificarUsuarioEntrada,
    admin: SoloAdministrador,
    servicio: ServicioUsuariosDep,
) -> UsuarioSalida:
    actualizado = await servicio.modificar(
        usuario_id, datos.a_datos(), ejecutor_id=admin.usuario_id
    )
    return UsuarioSalida(**actualizado)


@router.post("/api/usuarios/{usuario_id}/desactivar", response_model=UsuarioSalida)
async def desactivar_usuario(
    usuario_id: int, admin: SoloAdministrador, servicio: ServicioUsuariosDep
) -> UsuarioSalida:
    desactivado = await servicio.desactivar(usuario_id, ejecutor_id=admin.usuario_id)
    return UsuarioSalida(**desactivado)


@router.post("/api/usuarios/{usuario_id}/rol", response_model=UsuarioSalida)
async def asignar_rol(
    usuario_id: int,
    datos: AsignarRolEntrada,
    admin: SoloAdministrador,
    servicio: ServicioUsuariosDep,
) -> UsuarioSalida:
    actualizado = await servicio.asignar_rol(usuario_id, datos.rol, ejecutor_id=admin.usuario_id)
    return UsuarioSalida(**actualizado)


# ------------------------------ CU_USR_07: auditoria ------------------------

@router.get("/api/auditoria", response_model=list[EventoAuditoriaSalida])
async def consultar_auditoria(
    _sesion: AdministradorODuenio,
    uow: UoW,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    usuario_id: int | None = None,
    accion: str | None = None,
    entidad: str | None = None,
    limite: int = Query(default=200, le=1000),
) -> list[EventoAuditoriaSalida]:
    eventos = await auditoria.listar(
        uow,
        desde=desde,
        hasta=hasta,
        usuario_id=usuario_id,
        accion=accion,
        entidad=entidad,
        limite=limite,
    )
    return [EventoAuditoriaSalida(**e) for e in eventos]


@router.get("/api/auditoria/{evento_id}", response_model=EventoAuditoriaSalida)
async def detalle_auditoria(
    evento_id: int, _sesion: AdministradorODuenio, uow: UoW
) -> EventoAuditoriaSalida:
    evento = await auditoria.obtener(uow, evento_id)
    if evento is None:
        raise NoEncontrado("El evento de auditoria no existe")
    return EventoAuditoriaSalida(**evento)
