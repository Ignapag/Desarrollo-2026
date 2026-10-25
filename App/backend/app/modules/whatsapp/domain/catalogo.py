"""Referencias al catálogo vigente, sin inferir equivalencias semánticas."""

import re
import unicodedata


def normalizar(texto):
    return " ".join("".join(
        c for c in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(c) != "Mn"
    ).split()).strip(" .!¡?¿")


def _coincide_descripcion(producto, buscado):
    descripcion = producto.get("descripcion")
    if not isinstance(descripcion, str):
        return False
    genericas = {"de", "del", "la", "las", "el", "los", "un", "una", "con", "sin", "y"}
    if len([p for p in re.findall(r"\w+", buscado) if p not in genericas]) < 2:
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(buscado) + r"(?!\w)", normalizar(descripcion)))


def coincidencias_productos(productos, referencia):
    buscado = normalizar(str(referencia or ""))
    if not buscado:
        return []
    exactas = [p for p in productos if normalizar(p.get("nombre", "")) == buscado]
    parciales = [p for p in productos if buscado in normalizar(p.get("nombre", ""))]
    return exactas or parciales or [p for p in productos if _coincide_descripcion(p, buscado)]


def pregunta_producto_valida(texto):
    """Admite una pregunta breve; nunca HTML, enlaces ni instrucciones de comandos."""
    return (isinstance(texto, str) and 1 <= len(texto.strip()) <= 300
            and texto.strip().startswith("¿") and texto.strip().endswith("?")
            and texto.count("?") == texto.count("¿") == 1
            and not re.search(
                r"[a-z][a-z0-9+.-]*://|www\.|[<>\r\n$€£]|"
                r"cat[aá]logo\s+(?:N\b|\d+)|producto\s+(?:N\b|\d+)", texto, re.I,
            ))
