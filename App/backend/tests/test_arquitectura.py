"""Reglas estructurales de la arquitectura orientada a capacidades."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI

from app.registro_modulos import descubrir_routers, registrar_routers

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
RAIZ_REPO = RAIZ_BACKEND.parents[1]


def _imports(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8-sig"), filename=str(archivo))
    encontrados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            encontrados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            encontrados.add(nodo.module)
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
    infracciones: list[str] = []
    for archivo in (RAIZ_BACKEND / "app" / "modules").glob("*/domain/*.py"):
        if any(
            nombre == prefijo or nombre.startswith(f"{prefijo}.")
            for nombre in _imports(archivo)
            for prefijo in prefijos_prohibidos
        ):
            infracciones.append(str(archivo.relative_to(RAIZ_BACKEND)))
    assert not infracciones, f"dominio acoplado a infraestructura: {infracciones}"


def test_hay_un_unico_frontend_canonico() -> None:
    assert (RAIZ_REPO / "App" / "frontend").is_dir()
    assert not (RAIZ_REPO / "frontend").exists(), (
        "No agregar otro frontend en la raiz; integrar en App/frontend"
    )
