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
    restricciones: dict[str, tuple[str, list[str]]] = field(default_factory=dict, repr=False)


def _separar_sql(texto: str, separador: str = ",") -> list[str]:
    """Separa operaciones sin cortar expresiones, tipos ni literales SQL."""
    partes = []
    inicio = profundidad = 0
    en_literal = False
    for indice, caracter in enumerate(texto):
        if caracter == "'":
            en_literal = not en_literal
        elif not en_literal:
            if caracter == "(":
                profundidad += 1
            elif caracter == ")":
                profundidad -= 1
            elif caracter == separador and profundidad == 0:
                partes.append(texto[inicio:indice].strip())
                inicio = indice + 1
    partes.append(texto[inicio:].strip())
    return partes


def _agregar_restriccion(tabla: Tabla, definicion: str) -> None:
    nombre = None
    if coincidencia := re.match(r"CONSTRAINT\s+(\w+)\s+(.+)", definicion, re.I | re.S):
        nombre, definicion = coincidencia.groups()
    coincidencia = re.match(
        r"(PRIMARY KEY|UNIQUE|FOREIGN KEY)\s*\(([^)]+)\)", definicion, re.I
    )
    if coincidencia:
        clase = coincidencia.group(1).upper()
        nombres = [c.strip() for c in coincidencia.group(2).split(",")]
        sufijo = {"PRIMARY KEY": "pkey", "UNIQUE": "key", "FOREIGN KEY": "fkey"}[clase]
        nombre = nombre or (
            f"{tabla.nombre}_pkey" if clase == "PRIMARY KEY"
            else f"{tabla.nombre}_{'_'.join(nombres)}_{sufijo}"
        )
        tabla.restricciones[nombre] = (clase, nombres)
        for columna in tabla.columnas:
            if columna.nombre not in nombres:
                continue
            if clase == "PRIMARY KEY":
                columna.es_pk = columna.obligatoria = True
            elif clase == "UNIQUE" and len(nombres) == 1:
                columna.es_unica = True
            elif clase == "FOREIGN KEY":
                referencia = re.search(r"REFERENCES\s+(\w+)\s*\((\w+)\)", definicion, re.I)
                if referencia:
                    columna.referencia = ".".join(referencia.groups())
        if clase == "UNIQUE" and len(nombres) > 1:
            tabla.unicos.append(", ".join(nombres))
    elif re.match(r"CHECK\s*\(", definicion, re.I):
        # PostgreSQL usa tabla_check cuando el CHECK abarca varias columnas.
        expresion = re.sub(r"'[^']*'", "", definicion)
        nombres = [
            c.nombre for c in tabla.columnas
            if re.search(rf"\b{re.escape(c.nombre)}\b", expresion, re.I)
        ]
        base = tabla.nombre + (f"_{nombres[0]}" if len(nombres) == 1 else "") + "_check"
        if nombre is None:
            nombre = base
            indice = 1
            while nombre in tabla.restricciones:
                nombre = f"{base}{indice}"
                indice += 1
        tabla.restricciones[nombre] = ("CHECK", nombres)
    # Los CHECK enumerados se muestran en la columna, igual que en CREATE.
    for columna in tabla.columnas:
        valores = _valores_de_check(definicion, columna.nombre)
        if valores:
            columna.valores = valores


def _agregar_columna(tabla: Tabla, definicion: str) -> None:
    columna = _parsear_columna(definicion)
    if columna is None:
        _agregar_restriccion(tabla, definicion)
        return
    tabla.columnas.append(columna)
    for marca, activa in (("PRIMARY KEY", columna.es_pk), ("UNIQUE", columna.es_unica)):
        if activa:
            _agregar_restriccion(tabla, f"{marca} ({columna.nombre})")
    if columna.referencia:
        destino, atributo = columna.referencia.split(".")
        _agregar_restriccion(
            tabla, f"FOREIGN KEY ({columna.nombre}) REFERENCES {destino} ({atributo})"
        )
    # Los CHECK de columna también tienen nombre implícito en PostgreSQL;
    # registrarlos permite que una migración posterior los reemplace.
    if check := re.search(r"(?:CONSTRAINT\s+\w+\s+)?CHECK\s*\(.+\)", definicion, re.I | re.S):
        _agregar_restriccion(tabla, check.group())
    columna.valores = _valores_de_check(definicion, columna.nombre)


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

    if (defecto := re.search(
        r"DEFAULT\s+(.+?)(?:\s+(?:NOT NULL|REFERENCES|UNIQUE|PRIMARY|CHECK)|$)",
        resto, re.IGNORECASE,
    )):
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

        cuerpo = re.sub(r"--[^\n]*", "", cuerpo)
        for definicion in _separar_sql(cuerpo):
            _agregar_columna(tabla, definicion)

        tablas.append(tabla)

    return tablas


def parsear_esquema(archivos: list[Path]) -> list[Tabla]:
    """Aplica los ALTER usados por las migraciones; no es un parser SQL general.

    Admite ADD COLUMN/CONSTRAINT, DROP CONSTRAINT y ALTER COLUMN sobre
    obligatoriedad/default. Conserva la migración de creación para agrupar tablas.
    No interpreta funciones, índices, cambios de tipo ni identificadores citados.
    """
    tablas: dict[str, Tabla] = {}
    for archivo in sorted(archivos):
        tablas.update((tabla.nombre, tabla) for tabla in parsear(archivo))
        contenido = re.sub(r"--[^\n]*", "", archivo.read_text(encoding="utf-8"))
        for nombre, operaciones in re.findall(
            r"ALTER TABLE\s+(\w+)\s+([^;]+);", contenido, re.I
        ):
            tabla = tablas[nombre]
            for operacion in _separar_sql(operaciones):
                if agregar := re.match(r"ADD COLUMN\s+(.+)", operacion, re.I | re.S):
                    _agregar_columna(tabla, agregar.group(1))
                elif re.match(r"ADD\s+", operacion, re.I):
                    _agregar_restriccion(tabla, re.sub(r"^ADD\s+", "", operacion, flags=re.I))
                elif borrar := re.fullmatch(r"DROP CONSTRAINT\s+(\w+)", operacion, re.I):
                    clase, nombres = tabla.restricciones.pop(borrar.group(1))
                    for columna in tabla.columnas:
                        if columna.nombre in nombres:
                            if clase == "PRIMARY KEY":
                                columna.es_pk = False
                            elif clase == "UNIQUE":
                                columna.es_unica = False
                            elif clase == "FOREIGN KEY":
                                columna.referencia = None
                    if clase == "UNIQUE" and len(nombres) > 1:
                        tabla.unicos.remove(", ".join(nombres))
                elif alterar := re.fullmatch(
                    r"ALTER COLUMN\s+(\w+)\s+"
                    r"(SET NOT NULL|DROP NOT NULL|DROP DEFAULT|SET DEFAULT\s+.+)",
                    operacion, re.I | re.S,
                ):
                    columna = next(c for c in tabla.columnas if c.nombre == alterar.group(1))
                    accion = alterar.group(2)
                    if accion.upper() in {"SET NOT NULL", "DROP NOT NULL"}:
                        columna.obligatoria = accion.upper() == "SET NOT NULL"
                    elif accion.upper() == "DROP DEFAULT":
                        columna.default = None
                    else:
                        columna.default = re.sub(r"^SET DEFAULT\s+", "", accion, flags=re.I)
                else:
                    raise ValueError(f"ALTER TABLE no soportado en {archivo.name}: {operacion}")
    return list(tablas.values())


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
    esquema = parsear_esquema(archivos)
    total_tablas = 0

    indice: list[str] = ["## Índice de tablas", ""]
    cuerpo: list[str] = []

    for archivo in archivos:
        tablas = [tabla for tabla in esquema if tabla.archivo == archivo.stem]
        total_tablas += len(tablas)
        objetos = otros_objetos(archivo)

        titulo = archivo.stem.split("_", 1)[1].replace("_", " ").capitalize()
        cuerpo += [f"## {archivo.stem} — {titulo}", ""]
        enlaces = ", ".join(f"[`{t.nombre}`](#{t.nombre})" for t in tablas) or "sin tablas nuevas"
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
