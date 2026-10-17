"""Reglas estructurales de la arquitectura orientada a capacidades."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.dependencias import obtener_uow
from app.modules.usuarios.presentation.dependencias import usuario_actual
from app.registro_modulos import descubrir_routers, registrar_routers

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_BACKEND.parents[1]
RAIZ_MODULOS = RAIZ_BACKEND / "app" / "modules"


def _importa(archivo: Path, prefijos: tuple[str, ...]) -> bool:
    return any(
        nombre == prefijo or nombre.startswith(f"{prefijo}.")
        for nombre in _imports(archivo)
        for prefijo in prefijos
    )


def _depende_de(dependencia: Dependant, funcion: object) -> bool:
    return dependencia.call is funcion or any(
        _depende_de(sub, funcion) for sub in dependencia.dependencies
    )


def _imports(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8-sig"), filename=str(archivo))
    paquete = list(archivo.relative_to(RAIZ_BACKEND).with_suffix("").parts[:-1])
    encontrados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            encontrados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            # Los imports relativos se resuelven contra el paquete del archivo.
            base = paquete[: len(paquete) - nodo.level + 1] if nodo.level else []
            modulo = ".".join([*base, *([nodo.module] if nodo.module else [])])
            encontrados.add(modulo)
            # `from app.core import errores` tambien importa `app.core.errores`.
            encontrados.update(f"{modulo}.{alias.name}" for alias in nodo.names)
    return encontrados


def test_delivery_se_descubre_sin_registro_manual() -> None:
    routers = descubrir_routers()
    assert any(
        item.capacidad == "delivery"
        and item.modulo.endswith("delivery.presentation.router")
        for item in routers
    )


def test_las_rutas_descubiertas_no_se_duplican() -> None:
    aplicacion = FastAPI()
    registrar_routers(aplicacion)
    rutas: list[tuple[str, str]] = []
    for ruta in aplicacion.routes:
        for metodo in getattr(ruta, "methods", set()):
            if metodo not in {"HEAD", "OPTIONS"}:
                rutas.append((metodo, ruta.path))
    assert len(rutas) == len(set(rutas))


def test_core_no_importa_capacidades_de_negocio() -> None:
    infracciones: list[str] = []
    for archivo in (RAIZ_BACKEND / "app" / "core").glob("*.py"):
        if any(nombre.startswith("app.modules") for nombre in _imports(archivo)):
            infracciones.append(archivo.name)
    assert not infracciones, f"core depende de capacidades: {infracciones}"


def test_main_no_registra_capacidades_a_mano() -> None:
    imports_main = _imports(RAIZ_BACKEND / "app" / "main.py")
    assert not any(nombre.startswith("app.modules") for nombre in imports_main), (
        "main.py no debe importar capacidades; los routers se descubren automaticamente"
    )


def test_el_dominio_no_depende_de_frameworks() -> None:
    prefijos_prohibidos = ("fastapi", "pydantic", "psycopg", "app.core")
    infracciones = [
        str(archivo.relative_to(RAIZ_BACKEND))
        for archivo in RAIZ_MODULOS.glob("*/domain/*.py")
        if _importa(archivo, prefijos_prohibidos)
    ]
    assert not infracciones, f"dominio acoplado a infraestructura: {infracciones}"


def test_la_aplicacion_no_depende_de_http_ni_del_driver() -> None:
    """Los casos de uso lanzan errores de ``app.errores``; HTTP y psycopg quedan afuera."""
    prefijos_prohibidos = ("fastapi", "starlette", "pydantic", "psycopg", "app.core.errores")
    infracciones = [
        str(archivo.relative_to(RAIZ_BACKEND))
        for archivo in RAIZ_MODULOS.glob("*/application/*.py")
        if _importa(archivo, prefijos_prohibidos)
    ]
    assert not infracciones, f"aplicacion acoplada a HTTP o al driver: {infracciones}"


def test_ninguna_capacidad_importa_infraestructura_ajena() -> None:
    """Colaborar con otra capacidad se hace por su aplicacion o su composicion publica."""
    infracciones: list[str] = []
    for archivo in RAIZ_MODULOS.glob("*/**/*.py"):
        propia = archivo.relative_to(RAIZ_MODULOS).parts[0]
        for nombre in _imports(archivo):
            partes = nombre.split(".")
            if (
                len(partes) > 3
                and partes[:2] == ["app", "modules"]
                and partes[2] != propia
                and partes[3] == "infrastructure"
            ):
                infracciones.append(f"{archivo.relative_to(RAIZ_BACKEND)} -> {nombre}")
    assert not infracciones, f"infraestructura ajena importada: {infracciones}"


def test_las_guardas_de_sesion_se_resuelven_antes_que_la_conexion() -> None:
    """Una peticion sin sesion o sin rol se rechaza sin pedir una conexion al pool.

    FastAPI resuelve las dependencias en el orden de los parametros: la guarda
    (``Sesion``, ``PersonalInterno``...) tiene que declararse antes del servicio.
    """
    aplicacion = FastAPI()
    registrar_routers(aplicacion)
    infracciones: list[str] = []
    for ruta in aplicacion.routes:
        if not isinstance(ruta, APIRoute):
            continue
        dependencias = ruta.dependant.dependencies
        guardas = [i for i, d in enumerate(dependencias) if _depende_de(d, usuario_actual)]
        conexiones = [i for i, d in enumerate(dependencias) if _depende_de(d, obtener_uow)]
        if guardas and conexiones and guardas[-1] > conexiones[0]:
            infracciones.append(f"{sorted(ruta.methods)} {ruta.path}")
    assert not infracciones, f"guarda declarada despues del servicio: {infracciones}"


def test_hay_un_unico_frontend_canonico() -> None:
    assert (RAIZ_REPO / "App" / "frontend").is_dir()
    assert not (RAIZ_REPO / "frontend").exists(), (
        "No agregar otro frontend en la raiz; integrar en App/frontend"
    )
