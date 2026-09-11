"""Genera el diccionario de datos a partir de las migraciones SQL.

Es la referencia que usa el resto del grupo para programar contra el esquema:
nombres exactos de tablas y columnas, tipos, obligatoriedad, relaciones y
valores permitidos en cada CHECK.

Se genera del SQL y no a mano, para que no se desactualice: cada vez que se
agrega una migracion, se vuelve a correr.

Uso:
    python -m scripts.diccionario                 # escribe docs/DICCIONARIO_DATOS.md
    python -m scripts.diccionario --salida x.md   # a otro archivo
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.migrate import DIR_MIGRACIONES

RAIZ_APP = Path(__file__).resolve().parents[2]          # App/
RAIZ_REPO = RAIZ_APP.parent                             # raiz del repositorio
SALIDA_POR_DEFECTO = RAIZ_REPO / "docs" / "DICCIONARIO_DATOS.md"

PALABRAS_DE_RESTRICCION = (
    "CONSTRAINT",
    "PRIMARY KEY",
    "UNIQUE",
    "CHECK",
    "FOREIGN KEY",
)


@dataclass
class Columna:
    nombre: str
    tipo: str
    obligatoria: bool = False
    es_pk: bool = False
    es_unica: bool = False
    default: str | None = None
    referencia: str | None = None
    valores: list[str] = field(default_factory=list)


@dataclass
class Tabla:
    nombre: str
    archivo: str
    descripcion: str
    columnas: list[Columna] = field(default_factory=list)
    unicos: list[str] = field(default_factory=list)


def _descripcion_previa(lineas: list[str], indice: int) -> str:
    """Rescata el bloque de comentarios que precede al CREATE TABLE."""
    comentarios: list[str] = []
    i = indice - 1
    while i >= 0:
        linea = lineas[i].strip()
        if not linea or set(linea) <= {"-"}:
            i -= 1
            continue
        if linea.startswith("--"):
            texto = linea.lstrip("-").strip()
            if texto and not set(texto) <= {"-"}:
                comentarios.append(texto)
            i -= 1
            continue
        break
    return " ".join(reversed(comentarios))


def _valores_de_check(cuerpo: str, columna: str) -> list[str]:
    """Extrae los valores de un CHECK (columna IN ('A','B')) del cuerpo."""
    patron = re.compile(
        rf"CHECK\s*\(\s*{re.escape(columna)}\s+IN\s*\(([^)]*)\)", re.IGNORECASE
    )
    coincidencia = patron.search(cuerpo)
    if not coincidencia:
        return []
    return re.findall(r"'([^']*)'", coincidencia.group(1))


def _parsear_columna(linea: str) -> Columna | None:
    linea = linea.rstrip(",").strip()
    if not linea or linea.startswith("--"):
        return None
    if linea.upper().startswith(PALABRAS_DE_RESTRICCION):
        return None

    partes = linea.split()
    if len(partes) < 2:
        return None

    nombre, tipo = partes[0], partes[1]
    resto = " ".join(partes[2:])
    resto_mayus = resto.upper()

    # Tipos con parentesis: NUMERIC(12,2), VARCHAR(30)
    if tipo.endswith(")") is False and resto.startswith("("):
        tipo += resto.split(")")[0] + ")"

    columna = Columna(nombre=nombre, tipo=tipo)
    columna.es_pk = "PRIMARY KEY" in resto_mayus
    columna.es_unica = "UNIQUE" in resto_mayus
    columna.obligatoria = "NOT NULL" in resto_mayus or columna.es_pk

    if (defecto := re.search(r"DEFAULT\s+(.+?)(?:\s+(?:NOT NULL|REFERENCES|UNIQUE|PRIMARY)|$)",
                            resto, re.IGNORECASE)):
        columna.default = defecto.group(1).strip()

    if (ref := re.search(r"REFERENCES\s+(\w+)\s*\((\w+)\)", resto, re.IGNORECASE)):
        columna.referencia = f"{ref.group(1)}.{ref.group(2)}"

    if "GENERATED ALWAYS AS IDENTITY" in resto_mayus:
        columna.default = "autonumerico"

    return columna


def parsear(archivo: Path) -> list[Tabla]:
    contenido = archivo.read_text(encoding="utf-8")
    lineas = contenido.split("\n")
    tablas: list[Tabla] = []

    for numero, linea in enumerate(lineas):
        coincidencia = re.match(r"CREATE TABLE (\w+)\s*\(", linea)
        if not coincidencia:
            continue

        nombre = coincidencia.group(1)
        cuerpo_lineas: list[str] = []
        i = numero + 1
        while i < len(lineas) and not lineas[i].startswith(");"):
            cuerpo_lineas.append(lineas[i])
            i += 1
        cuerpo = "\n".join(cuerpo_lineas)

        tabla = Tabla(
            nombre=nombre,
            archivo=archivo.stem,
            descripcion=_descripcion_previa(lineas, numero),
        )

        for cuerpo_linea in cuerpo_lineas:
            columna = _parsear_columna(cuerpo_linea)
            if columna is None:
                continue
            columna.valores = _valores_de_check(cuerpo, columna.nombre)
            tabla.columnas.append(columna)

        # Claves foraneas declaradas a nivel tabla
        for ref_columna, ref_tabla, ref_destino in re.findall(
            r"FOREIGN KEY \((\w+)\) REFERENCES (\w+)\s*\((\w+)\)", cuerpo, re.IGNORECASE
        ):
            for columna in tabla.columnas:
                if columna.nombre == ref_columna and not columna.referencia:
                    columna.referencia = f"{ref_tabla}.{ref_destino}"

        # PRIMARY KEY (a, b) a nivel tabla
        if (pk := re.search(r"PRIMARY KEY \(([^)]+)\)", cuerpo, re.IGNORECASE)):
            for parte in pk.group(1).split(","):
                for columna in tabla.columnas:
                    if columna.nombre == parte.strip():
                        columna.es_pk = True
                        columna.obligatoria = True

        for unico in re.findall(r"UNIQUE \(([^)]+)\)", cuerpo, re.IGNORECASE):
            tabla.unicos.append(unico.strip())

        tablas.append(tabla)

    return tablas


def otros_objetos(archivo: Path) -> dict[str, list[str]]:
    contenido = archivo.read_text(encoding="utf-8")
    return {
        "vistas": re.findall(r"CREATE OR REPLACE VIEW (\w+)", contenido),
        "funciones": re.findall(r"CREATE OR REPLACE FUNCTION (\w+)", contenido),
        "triggers": re.findall(r"CREATE TRIGGER (\w+)", contenido),
    }


def _fila_columna(columna: Columna) -> str:
    marcas = []
    if columna.es_pk:
        marcas.append("PK")
    if columna.es_unica:
        marcas.append("único")
    if columna.referencia:
        marcas.append(f"FK → `{columna.referencia}`")

    notas = " · ".join(marcas)
    if columna.valores:
        valores = ", ".join(f"`{v}`" for v in columna.valores)
        notas = f"{notas} · " if notas else ""
        notas += f"valores: {valores}"
    if columna.default and columna.default != "autonumerico":
        notas += f" · default `{columna.default}`" if notas else f"default `{columna.default}`"
    elif columna.default == "autonumerico":
        notas += " · autonumérico" if notas else "autonumérico"

    return (
        f"| `{columna.nombre}` | {columna.tipo} | "
        f"{'Sí' if columna.obligatoria else 'No'} | {notas or '—'} |"
    )


def generar() -> str:
    partes: list[str] = [
        "# Diccionario de datos — Monu Burger",
        "",
        "Referencia del esquema para todo el grupo: nombres exactos de tablas y",
        "columnas, tipos, obligatoriedad, relaciones y valores permitidos.",
        "",
        "> **Generado automáticamente** con `python -m scripts.diccionario` a partir",
        "> de `App/db/migrations/`. No editar a mano: cada vez que se agrega una",
        "> migración, volver a generarlo. CI verifica que este al dia.",
        "",
        "## Reglas de uso",
        "",
        "- Los nombres van en **español** y `snake_case`. Respetarlos tal cual: si tu",
        "  módulo inventa nombres, la integración no cierra.",
        "- Toda consulta va **parametrizada** (`%s`). Nunca interpolar valores.",
        "- Los montos son `NUMERIC(12,2)` y las cantidades `NUMERIC(12,3)`: en Python",
        "  llegan como `Decimal`, no como `float`.",
        "- Las fechas son `TIMESTAMPTZ` (con zona horaria).",
        "- **Nadie modifica una migración ya aplicada.** Si necesitás un cambio de",
        "  esquema, pedilo: se agrega una migración nueva numerada.",
        "",
    ]

    archivos = sorted(DIR_MIGRACIONES.glob("*.sql"))
    total_tablas = 0

    indice: list[str] = ["## Índice de tablas", ""]
    cuerpo: list[str] = []

    for archivo in archivos:
        tablas = parsear(archivo)
        total_tablas += len(tablas)
        objetos = otros_objetos(archivo)

        titulo = archivo.stem.split("_", 1)[1].replace("_", " ").capitalize()
        cuerpo += [f"## {archivo.stem} — {titulo}", ""]
        enlaces = ", ".join(f"[`{t.nombre}`](#{t.nombre})" for t in tablas)
        indice += [f"**{titulo}** — {enlaces}", ""]

        for tabla in tablas:
            cuerpo += [f"### {tabla.nombre}", ""]
            if tabla.descripcion:
                cuerpo += [f"_{tabla.descripcion}_", ""]
            cuerpo += [
                "| Columna | Tipo | Obligatoria | Notas |",
                "|---------|------|-------------|-------|",
            ]
            cuerpo += [_fila_columna(c) for c in tabla.columnas]
            if tabla.unicos:
                cuerpo += ["", "Únicos: " + ", ".join(f"`({u})`" for u in tabla.unicos)]
            cuerpo += [""]

        for clave, etiqueta in (
            ("vistas", "Vistas"),
            ("funciones", "Funciones"),
            ("triggers", "Triggers"),
        ):
            if objetos[clave]:
                cuerpo += [
                    f"**{etiqueta}:** " + ", ".join(f"`{o}`" for o in objetos[clave]),
                    "",
                ]

    partes += indice + [f"Total: **{total_tablas} tablas**.", "", "---", ""] + cuerpo
    return "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el diccionario de datos")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    args = parser.parse_args()

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(generar(), encoding="utf-8")
    print(f"Diccionario escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
