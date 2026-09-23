"""Pruebas de control de acceso (tarea de Autenticacion y Roles).

Prueban `requiere_rol()` y sus alias (PersonalInterno, SoloAdministrador,
etc.) llamando la funcion de guarda directamente con un ClaimsSesion falso:
no dependen de HTTP ni de la base, asi que corren siempre y son la cobertura
mas rapida y completa de la matriz rol -> endpoint.

`test_usuarios_http.py` complementa esto contra la API real, para verificar
que cada endpoint efectivamente tiene el alias correcto declarado.
"""

from __future__ import annotations

import pytest

from app.core.dependencias import requiere_rol
from app.core.errores import SinPermiso
from app.modules.usuarios.domain.entidades import ROLES_PERSONAL_INTERNO, ClaimsSesion, Rol


def claims(rol: Rol) -> ClaimsSesion:
    return ClaimsSesion(usuario_id=1, rol=rol, username="prueba")


def test_requiere_rol_permite_el_rol_exacto():
    guardia = requiere_rol(Rol.ADMINISTRADOR)
    sesion = claims(Rol.ADMINISTRADOR)
    assert guardia(sesion) is sesion


def test_requiere_rol_rechaza_un_rol_distinto():
    guardia = requiere_rol(Rol.ADMINISTRADOR)
    with pytest.raises(SinPermiso):
        guardia(claims(Rol.CLIENTE))


def test_requiere_rol_acepta_cualquiera_de_varios():
    guardia = requiere_rol(Rol.ADMINISTRADOR, Rol.DUENIO)
    assert guardia(claims(Rol.ADMINISTRADOR)) is not None
    assert guardia(claims(Rol.DUENIO)) is not None
    with pytest.raises(SinPermiso):
        guardia(claims(Rol.EMPLEADO))


@pytest.mark.parametrize("rol", list(ROLES_PERSONAL_INTERNO))
def test_personal_interno_acepta_todo_menos_cliente(rol: Rol):
    guardia = requiere_rol(*ROLES_PERSONAL_INTERNO)
    assert guardia(claims(rol)) is not None


def test_personal_interno_rechaza_al_cliente():
    guardia = requiere_rol(*ROLES_PERSONAL_INTERNO)
    with pytest.raises(SinPermiso):
        guardia(claims(Rol.CLIENTE))


def test_cliente_no_es_personal_interno():
    """El Cliente es el unico rol afuera de PersonalInterno (ver dominio)."""
    assert Rol.CLIENTE not in ROLES_PERSONAL_INTERNO
    assert len(ROLES_PERSONAL_INTERNO) == len(Rol) - 1
