"""Seguridad de fronteras HTTP, sin conexión de base para los rechazos."""

import hashlib
import hmac
import json
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.core.seguridad import crear_token
from app.errores import ErrorDominio
from app.modules.usuarios.presentation.dependencias import sesion_vigente, usuario_actual
from app.modules.whatsapp.presentation.router import router


def aplicacion():
    app = FastAPI()
    # Identidad sintetica: esta suite verifica negocio, no resolucion de sesiones.
    app.dependency_overrides[sesion_vigente] = usuario_actual
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)
    app.include_router(router)
    return app


@pytest.mark.parametrize("rol", [None, "CLIENTE", "REPARTIDOR"])
@pytest.mark.parametrize(
    "ruta,metodo",
    [
        ("/bandeja", "get"),
        ("/comprobantes/1/archivo", "get"),
        ("/comprobantes/1/revision", "post"),
        ("/cambios/1/revision", "post"),
        ("/atenciones/1/respuesta", "post"),
        ("/atenciones/1/resolucion", "post"),
    ],
)
def test_cliente_y_repartidor_no_revisan_ni_descargan(rol, ruta, metodo):
    app = aplicacion()

    async def no_conectar():
        pytest.fail("No debe solicitar una conexión para un rol rechazado")

    app.dependency_overrides[obtener_uow] = no_conectar
    with TestClient(app) as cliente:
        if rol:
            cliente.cookies.set(
                settings.cookie_sesion, crear_token(usuario_id=1, rol=rol, username="prueba")
            )
        cuerpos = {
            "/atenciones/1/respuesta": {
                "texto": "Hola", "solicitud_id": "0f8e1c1e-6b65-4d2e-8f39-5b1a1d2c3e4f"
            },
            "/atenciones/1/resolucion": {"resolucion": "Resuelto por teléfono"},
        }
        cuerpo = cuerpos.get(ruta, {"aprobar": True, "motivo": "verificado"})
        respuesta = getattr(cliente, metodo)(
            "/api/whatsapp" + ruta, **({"json": cuerpo} if metodo == "post" else {})
        )
        assert respuesta.status_code == (403 if rol else 401)


@pytest.mark.parametrize("firma", [None, "sha256=invalido", "", "sha256=å"])
def test_firma_invalida_no_conecta(monkeypatch, firma):
    from app.modules.whatsapp.presentation import router as modulo

    @asynccontextmanager
    async def no_conectar():
        pytest.fail("Firma inválida no debe abrir conexión")
        yield

    monkeypatch.setattr(modulo, "conexion", no_conectar)
    monkeypatch.setattr(settings, "whatsapp_modo", "real")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "secret-prueba")
    with TestClient(aplicacion()) as cliente:
        respuesta = cliente.post(
            "/api/whatsapp/webhook",
            content=b"{}",
            headers={"x-hub-signature-256": firma.encode("latin1")} if firma else {},
        )
        assert respuesta.status_code == 403


def test_precios_frontend_no_se_admiten():
    from pydantic import ValidationError

    from app.modules.whatsapp.presentation.esquemas import BorradorEntrada

    with pytest.raises(ValidationError):
        BorradorEntrada(
            telefono="5492215550000", items=[{"producto_id": 1, "cantidad": 1, "precio": "0.01"}]
        )


@pytest.mark.asyncio
async def test_webhook_firmado_repetido_persiste_entrada_unica(uow, monkeypatch):
    import httpx

    from app.modules.whatsapp.presentation import router as modulo

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    monkeypatch.setattr(modulo, "conexion", conexion_prueba)
    monkeypatch.setattr(settings, "whatsapp_modo", "real")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "secret-prueba")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "numero-prueba")
    cuerpo = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "numero-prueba"},
                                "messages": [
                                    {
                                        "id": "repetido-http",
                                        "from": "5492215550000",
                                        "type": "text",
                                        "text": {"body": "retiro"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }
    ).encode()
    firma = "sha256=" + hmac.new(b"secret-prueba", cuerpo, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=aplicacion()), base_url="http://prueba"
    ) as cliente:
        for _ in range(2):
            respuesta = await cliente.post(
                "/api/whatsapp/webhook", content=cuerpo, headers={"x-hub-signature-256": firma}
            )
            assert respuesta.status_code == 200
    assert await uow.valor("SELECT count(*) FROM whatsapp_entrada WHERE id='repetido-http'") == 1


@pytest.mark.asyncio
async def test_webhook_conserva_pie_de_foto_del_comprobante(uow, monkeypatch):
    import httpx

    from app.modules.whatsapp.presentation import router as modulo

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    monkeypatch.setattr(modulo, "conexion", conexion_prueba)
    monkeypatch.setattr(settings, "whatsapp_modo", "real")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "secret-prueba")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "numero-prueba")
    mensaje = {
        "id": "foto-con-pie",
        "from": "5492215550000",
        "type": "image",
        "image": {"id": "12345", "caption": "Comprobante del pedido MB-referencia"},
    }
    cuerpo = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "numero-prueba"},
                                "messages": [mensaje],
                            }
                        }
                    ]
                }
            ],
        }
    ).encode()
    firma = "sha256=" + hmac.new(b"secret-prueba", cuerpo, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=aplicacion()), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.post(
            "/api/whatsapp/webhook", content=cuerpo, headers={"x-hub-signature-256": firma}
        )
    assert respuesta.status_code == 200
    fila = await uow.uno("SELECT texto,media_id FROM whatsapp_entrada WHERE id='foto-con-pie'")
    assert fila == {"texto": "Comprobante del pedido MB-referencia", "media_id": "12345"}
