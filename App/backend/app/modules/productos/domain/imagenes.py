"""Validación de la referencia o imagen raster que se guarda en un producto."""

import base64
import binascii
from urllib.parse import urlsplit

MAX_IMAGEN_BYTES = 5 * 1024 * 1024


def validar_imagen_producto(valor: str | None) -> str | None:
    """Admite referencias web/locales y raster embebido de hasta cinco MiB."""
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str):
        raise ValueError("La imagen no es valida")
    if valor.startswith("data:"):
        if len(valor) > (MAX_IMAGEN_BYTES + 2) // 3 * 4 + 64:
            raise ValueError("La imagen no puede superar 5 MiB")
        cabecera, separador, contenido = valor.partition(",")
        formatos = {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
            "data:image/gif;base64",
            "data:image/avif;base64",
        }
        if not separador or cabecera not in formatos:
            raise ValueError("Usa una imagen PNG, JPEG, WebP, GIF o AVIF")
        try:
            datos = base64.b64decode(contenido, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Los datos de la imagen no son validos") from exc
        if not datos or len(datos) > MAX_IMAGEN_BYTES:
            raise ValueError("La imagen debe contener datos y no superar 5 MiB")
        firmas = {
            "data:image/png;base64": datos.startswith(b"\x89PNG\r\n\x1a\n"),
            "data:image/jpeg;base64": datos.startswith(b"\xff\xd8\xff"),
            "data:image/webp;base64": datos.startswith(b"RIFF") and datos[8:12] == b"WEBP",
            "data:image/gif;base64": datos.startswith((b"GIF87a", b"GIF89a")),
            "data:image/avif;base64": datos[4:8] == b"ftyp"
            and any(m in datos[8:40] for m in (b"avif", b"avis")),
        }
        if not firmas[cabecera]:
            raise ValueError("El contenido no coincide con el formato de la imagen")
        return valor
    if len(valor) > 2048 or any(c.isspace() or ord(c) < 32 for c in valor) or "\\" in valor:
        raise ValueError("La direccion de la imagen no es valida")
    url = urlsplit(valor)
    local = valor.startswith("/") and not valor.startswith("//")
    remota = (
        url.scheme in {"http", "https"}
        and bool(url.hostname)
        and not url.username
        and not url.password
    )
    if not (local or remota) or url.path.casefold().endswith((".svg", ".svgz", ".html", ".htm")):
        raise ValueError("Usa una URL http(s), una ruta local o una imagen raster")
    return valor
