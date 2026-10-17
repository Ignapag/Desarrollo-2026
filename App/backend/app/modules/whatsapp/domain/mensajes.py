"""Referencias opacas, mensajes deterministas y límites de interpretación."""

import hashlib
import re

from app.modules.whatsapp.domain.textos import INICIO_WEB, resumen_pedido

# Límite del texto que puede interpretarse; el receptor admite hasta 4096 caracteres.
LIMITE_INTERPRETACION = 2000
SALUDO_BORRADOR = "Hola Monu Burger, quiero confirmar mi borrador"

_REFERENCIA = re.compile(r"\bMB-([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])")
# Todo token con forma de referencia se retira antes de interpretar: nunca sale al proveedor.
# Cubre variantes de escritura (minúsculas, espacio o guiones Unicode) del token de 43
# caracteres; el largo mínimo evita confundirlo con palabras como "hamburguesa".
_TOKEN_REFERENCIA = re.compile(
    r"MB[\s\u2010-\u2015\u2212-]*[A-Za-z0-9_-]{30,}|\bMB-[A-Za-z0-9_-]*", re.I
)
_COMANDO_GUIADO = re.compile(r"producto\s+\d+(?:\s*;\s*variante:\s*.{1,60})?[.!]?", re.I)
_NUMERO_PEDIDO = re.compile(r"\b(?:(?:para\s+el|del|el)\s+)?pedido\s*#\s*(\d+)\b", re.I)


def telefono_canonico(telefono: str) -> str:
    """La variante argentina 54/549 representa el mismo WhatsApp móvil."""
    return "549" + telefono[2:] if telefono.startswith("54") and len(telefono) == 12 else telefono


def huella_inicio(telefono: str, texto: str) -> str:
    contenido = telefono_canonico(telefono) + "\n" + " ".join(texto.split()).casefold()
    return hashlib.sha256(contenido.encode()).hexdigest()


def es_inicio_web(texto: str) -> bool:
    normal = " ".join(texto.split()).casefold()
    return normal.startswith(" ".join(INICIO_WEB.split()).casefold()) or (
        "subtotal estimado:" in normal and "armé mi pedido el" in normal
    )


def numeros_pedido_en(texto: str) -> set[int]:
    return {int(n) for n in _NUMERO_PEDIDO.findall(texto)}


def sin_selector_pedido(texto: str) -> str:
    return " ".join(_NUMERO_PEDIDO.sub(" ", texto).split())


def hash_referencia(referencia: str) -> str:
    return hashlib.sha256(referencia.encode()).hexdigest()


def referencias_en(texto: str) -> set[str]:
    return set(_REFERENCIA.findall(texto))


def referencia_en(texto: str) -> str | None:
    """Referencia única del mensaje; dos referencias distintas no seleccionan ninguna."""
    referencias = referencias_en(texto)
    return referencias.pop() if len(referencias) == 1 else None


def tiene_token_referencia(texto: str) -> bool:
    return bool(_TOKEN_REFERENCIA.search(texto))


def sin_referencias(texto: str) -> str:
    """Texto completo sin los identificadores de acceso; no recorta instrucciones."""
    return " ".join(_TOKEN_REFERENCIA.sub(" ", texto).split())


def ocultar_referencias(texto: str) -> str:
    """Versión para personal: conserva el mensaje y oculta el identificador de acceso."""
    return _TOKEN_REFERENCIA.sub("[referencia]", texto)


def es_comando_guiado(texto: str) -> bool:
    return bool(_COMANDO_GUIADO.fullmatch(texto.strip()))


def es_saludo_borrador(texto: str) -> bool:
    """Mensaje preparado por la web, sin instrucciones adicionales del cliente."""
    normal = re.sub(r"[^\w]+", " ", texto.casefold()).strip()
    return normal in {"", re.sub(r"[^\w]+", " ", SALUDO_BORRADOR.casefold()).strip()}


def resumen(pedido: dict) -> str:
    return resumen_pedido(pedido)
