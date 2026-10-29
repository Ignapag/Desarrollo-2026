"""Dependencias HTTP transversales, sin conocimiento de capacidades."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from ipaddress import ip_address, ip_network
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.db import UnidadDeTrabajo, conexion


async def obtener_uow(request: Request) -> AsyncIterator[UnidadDeTrabajo]:
    """Una transaccion por request: commit al terminar, rollback si hay error."""
    async with conexion() as conn:
        uow = UnidadDeTrabajo(conn)
        origen = "chat_demo" if request.url.path.startswith("/api/chat-demo/") else "http"
        await uow.configurar_auditoria(origen=origen, ip=ip_cliente(request))
        yield uow


UoW = Annotated[UnidadDeTrabajo, Depends(obtener_uow)]


#: Cabeceras que agrega `App/frontend/functions/api/[[path]].js` desde ``CF-Connecting-IP``.
CABECERA_IP_PROXY = "x-monu-ip-cliente"
CABECERA_SECRETO_PROXY = "x-monu-proxy-secreto"
#: Origen común de las peticiones sin proxy autenticado cuando el secreto está configurado.
ORIGEN_SIN_PROXY = "sin-proxy"
PREFIJO_IPV6_LIMITE = 64


def _normalizar_ip(valor: str | None) -> str | None:
    """Normaliza una IP y descarta valores vacíos, mal formados o con zona IPv6.

    PostgreSQL ``inet`` no admite zonas (``fe80::1%eth0``) y una IP pública nunca la lleva.
    """
    if not valor or "%" in valor:
        return None
    try:
        return str(ip_address(valor.strip()))
    except ValueError:
        return None


def ip_de_proxy_confiable(request: Request) -> str | None:
    """IP enviada por la Function de Pages, solo si trae el secreto compartido.

    Es la única cabecera de IP que el backend considera confiable: Pages la toma
    de ``CF-Connecting-IP`` (lo fija el edge de Cloudflare) y descarta la copia
    que mande el visitante. Sin ``PROXY_IP_SECRETO`` configurado nunca se usa.
    """
    secreto = settings.proxy_ip_secreto
    recibido = request.headers.get(CABECERA_SECRETO_PROXY)
    if not secreto or recibido is None:
        return None
    if not hmac.compare_digest(recibido.encode("utf-8"), secreto.encode("utf-8")):
        return None
    return _normalizar_ip(request.headers.get(CABECERA_IP_PROXY))


def ip_cliente(request: Request) -> str | None:
    """Obtiene la IP del cliente para auditoría.

    Prioriza la IP autenticada del proxy de Pages. Si no viene, conserva el
    criterio informativo anterior: primer valor de ``X-Forwarded-For`` o la IP de
    la conexión. Ese valor lo puede falsificar el cliente, por eso los límites de
    seguridad usan ``origen_para_limite`` y no esta función.
    """
    confiable = ip_de_proxy_confiable(request)
    if confiable is not None:
        return confiable
    reenviado = request.headers.get("x-forwarded-for")
    candidato = reenviado.split(",")[0] if reenviado else None
    if candidato is None and request.client:
        candidato = request.client.host
    return _normalizar_ip(candidato)


def origen_para_limite(request: Request) -> str | None:
    """Origen que cuenta para los límites por IP; nunca lee ``X-Forwarded-For``.

    Sin secreto configurado devuelve ``None`` (no hay IP confiable y el límite por
    IP no se aplica). Con secreto, las peticiones sin proxy autenticado (directas a
    Render, o con secreto inválido) comparten ``ORIGEN_SIN_PROXY``: falsificar o
    quitar cabeceras no da un cupo nuevo. IPv6 cuenta por su red /64, la unidad
    que se asigna a un cliente, para que rotar direcciones tampoco lo dé.
    """
    if not settings.proxy_ip_secreto:
        return None
    ip = ip_de_proxy_confiable(request)
    if ip is None:
        return ORIGEN_SIN_PROXY
    if ip_address(ip).version == 6:
        return str(ip_network(f"{ip}/{PREFIJO_IPV6_LIMITE}", strict=False))
    return ip


IpCliente = Annotated[str | None, Depends(ip_cliente)]
OrigenLimite = Annotated[str | None, Depends(origen_para_limite)]
