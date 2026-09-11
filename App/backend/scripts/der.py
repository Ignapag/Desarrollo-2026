"""Genera el diagrama entidad-relacion a partir de las migraciones SQL.

Produce docs/DER.md con diagramas Mermaid, que GitHub renderiza solo. Al
generarse del SQL, el diagrama no puede quedar desactualizado respecto del
esquema real: cada vez que se agrega una migracion, se vuelve a correr.

Emite tres cosas:
  1. Un diagrama general con todas las entidades y sus relaciones.
  2. Un diagrama por modulo, con los atributos de cada tabla.
  3. La lista de relaciones en tabla, para citar en el informe.

Uso:
    python -m scripts.der
    python -m scripts.der --salida otro.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from scripts.diccionario import RAIZ_REPO, Tabla, parsear
from scripts.migrate import DIR_MIGRACIONES

SALIDA_POR_DEFECTO = RAIZ_REPO / "docs" / "DER.md"

#: Mermaid no acepta parentesis ni comas en el tipo del atributo.
def _tipo_mermaid(tipo: str) -> str:
    return tipo.split("(")[0].lower()


def _titulo(archivo_stem: str) -> str:
    return archivo_stem.split("_", 1)[1].replace("_", " ").capitalize()


def _relaciones(tablas: list[Tabla]) -> list[tuple[str, str, str, bool, bool]]:
    """(tabla_origen, tabla_destino, columna, obligatoria, es_uno_a_uno)."""
    salida = []
    for tabla in tablas:
        # Si la PK es una sola columna y ademas es FK, la relacion es 1:1
        # (es el caso de los subtipos: repartidor y cliente con usuario).
        # Con PK compuesta no aplica: ahi cada columna se repite.
        columnas_pk = [c for c in tabla.columnas if c.es_pk]
        pk_simple = len(columnas_pk) == 1

        for columna in tabla.columnas:
            if not columna.referencia:
                continue
            destino = columna.referencia.split(".")[0]
            uno_a_uno = columna.es_unica or (columna.es_pk and pk_simple)
            salida.append(
                (tabla.nombre, destino, columna.nombre, columna.obligatoria, uno_a_uno)
            )
    return salida


def _linea_relacion(
    origen: str, destino: str, columna: str, obligatoria: bool, uno_a_uno: bool
) -> str:
    """Cardinalidad en notacion Mermaid.

    El lado del destino es siempre uno; si la FK admite nulos, es "cero o uno".
    El lado del origen es "muchos", salvo que la FK sea unica.
    """
    lado_destino = "||" if obligatoria else "o|"
    lado_origen = "||" if uno_a_uno else "o{"
    return f"    {destino.upper()} {lado_destino}--{lado_origen} {origen.upper()} : {columna}"


def generar() -> str:
    archivos = sorted(DIR_MIGRACIONES.glob("*.sql"))
    por_archivo: dict[str, list[Tabla]] = {}
    todas: list[Tabla] = []

    for archivo in archivos:
        tablas = parsear(archivo)
        if tablas:
            por_archivo[archivo.stem] = tablas
            todas.extend(tablas)

    relaciones = _relaciones(todas)

    partes: list[str] = [
        "# Diagrama Entidad-Relación — Monu Burger",
        "",
        "Modelo de datos **tal como está implementado** en la base.",
        "",
        "> **Generado automáticamente** con `python -m scripts.der` a partir de",
        "> `App/db/migrations/`. No editar a mano: al derivarse del SQL, no puede",
        "> quedar desactualizado respecto del esquema real.",
        f"> Última generación: {date.today().isoformat()}.",
        "",
        f"**{len(todas)} entidades · {len(relaciones)} relaciones.**",
        "",
        "Este diagrama reemplaza al entregado en la Actividad N°2: las diferencias",
        "están explicadas una por una en [CAMBIOS_DER.md](CAMBIOS_DER.md) (C-01 a C-12).",
        "",
        "## Cómo leer la notación",
        "",
        "| Símbolo | Significado |",
        "|---------|-------------|",
        "| `\\|\\|--o{` | uno a muchos (la relación es obligatoria) |",
        "| `o\\|--o{` | uno a muchos (la clave foránea admite nulos) |",
        "| `\\|\\|--\\|\\|` | uno a uno |",
        "| `PK` | clave primaria · `FK` clave foránea · `UK` valor único |",
        "",
        "---",
        "",
        "## Diagrama general",
        "",
        "Entidades y relaciones, sin atributos.",
        "",
        "```mermaid",
        "erDiagram",
    ]

    for origen, destino, columna, obligatoria, uno_a_uno in relaciones:
        partes.append(_linea_relacion(origen, destino, columna, obligatoria, uno_a_uno))

    partes += ["```", "", "---", "", "## Diagramas por módulo", ""]

    for stem, tablas in por_archivo.items():
        nombres = {t.nombre for t in tablas}
        partes += [f"### {_titulo(stem)}", "", "```mermaid", "erDiagram"]

        for origen, destino, columna, obligatoria, uno_a_uno in relaciones:
            if origen in nombres and destino in nombres:
                partes.append(_linea_relacion(origen, destino, columna, obligatoria, uno_a_uno))

        for tabla in tablas:
            partes.append(f"    {tabla.nombre.upper()} {{")
            for columna in tabla.columnas:
                marca = "PK" if columna.es_pk else ("FK" if columna.referencia else "")
                if not marca and columna.es_unica:
                    marca = "UK"
                partes.append(
                    f"        {_tipo_mermaid(columna.tipo)} {columna.nombre} {marca}".rstrip()
                )
            partes.append("    }")

        partes += ["```", ""]

    partes += [
        "---",
        "",
        "## Relaciones en detalle",
        "",
        "| Desde | Clave foránea | Hacia | Cardinalidad | Obligatoria |",
        "|-------|---------------|-------|--------------|-------------|",
    ]
    for origen, destino, columna, obligatoria, uno_a_uno in sorted(relaciones):
        cardinalidad = "1 : 1" if uno_a_uno else "1 : N"
        partes.append(
            f"| `{origen}` | `{columna}` | `{destino}` | {cardinalidad} | "
            f"{'Sí' if obligatoria else 'No'} |"
        )

    partes += [
        "",
        "---",
        "",
        "## Para el informe",
        "",
        "Los diagramas de arriba se renderizan solos en GitHub. Para pegarlos en el",
        "documento de la entrega, copiar el bloque `mermaid` correspondiente en",
        "[mermaid.live](https://mermaid.live) y exportarlo como PNG o SVG.",
        "",
    ]
    return "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera el diagrama entidad-relacion")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    args = parser.parse_args()

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(generar(), encoding="utf-8")
    print(f"DER escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
