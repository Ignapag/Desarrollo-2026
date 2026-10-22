"""Canal web: sesión anónima, persistencia y operaciones del bot real."""

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from app.core.config import settings
from app.core.dependencias import obtener_uow
from app.core.errores import manejador_error_dominio
from app.errores import ErrorDominio


@pytest_asyncio.fixture
async def chat(uow, monkeypatch):
    from app.modules.whatsapp.presentation.router_demo import router

    monkeypatch.setattr(settings, "chat_demo_habilitado", True)
    monkeypatch.setattr(settings, "whatsapp_modo", "simulado")
    monkeypatch.setattr(settings, "gemini_modo", "simulado")
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def unidad():
        yield uow

    app.dependency_overrides[obtener_uow] = unidad
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
        headers={"X-Chat-Demo": "1"},
    ) as cliente:
        yield cliente


async def iniciar(chat):
    respuesta = await chat.post("/api/chat-demo/sesion", json={})
    assert respuesta.status_code == 200, respuesta.text
    return chat.cookies.get("monu_chat_demo")


async def carrito(uow, chat, pago=None, solicitud=None):
    from tests.test_whatsapp_bd import datos_prueba

    _, item = await datos_prueba(uow)
    cuerpo = {
        "solicitud_id": solicitud or str(uuid4()),
        "borrador": {
            "items": [item],
            "tipo_entrega": None,
            "metodo_pago": pago,
            "contacto": {"nombre": "Cliente", "apellido": "Demo", "telefono": "5492215550987"},
        },
    }
    respuesta = await chat.post("/api/chat-demo/borradores", json=cuerpo)
    assert respuesta.status_code == 202, respuesta.text
    return cuerpo, respuesta.json()["id"]


async def procesar(uow, identificador, accion=None):
    from app.modules.whatsapp.presentation.dependencias import construir_servicio

    servicio = construir_servicio(uow)
    preparado = await servicio.preparar(identificador)
    if preparado:
        await servicio.procesar(
            identificador,
            accion or {"accion": "consulta", "argumentos": {}},
            preparado["vinculo"],
        )


async def enviar(chat, texto, solicitud=None):
    respuesta = await chat.post(
        "/api/chat-demo/mensajes",
        json={
            "solicitud_id": solicitud or str(uuid4()),
            "texto": texto,
        },
    )
    assert respuesta.status_code == 202, respuesta.text
    return respuesta.json()["id"]


@pytest.mark.asyncio
async def test_sesion_cookie_persistida_aisla_mismo_contacto_y_recarga(chat, uow):
    cookie = await iniciar(chat)
    _, entrada = await carrito(uow, chat)
    await procesar(uow, entrada)
    historial = (await chat.get("/api/chat-demo/conversacion")).json()
    assert len(historial["mensajes"]) == 2
    assert historial["borradores"][0]["pedido_id"] is None
    assert "×" in historial["mensajes"][0]["texto"]
    assert historial["borradores"][0]["items"][0]["nombre"]
    assert "MB-" not in str(historial)
    assert not await uow.valor(
        "SELECT EXISTS(SELECT 1 FROM cliente WHERE whatsapp_verificado='5492215550987')"
    )
    chat.cookies.clear()
    assert (await chat.get("/api/chat-demo/conversacion")).status_code == 401
    await iniciar(chat)
    assert (await chat.get("/api/chat-demo/conversacion")).json()["mensajes"] == []
    _, otra_entrada = await carrito(uow, chat)
    assert otra_entrada != entrada
    chat.cookies.clear()
    chat.cookies.set("monu_chat_demo", cookie)
    recuperado = (await chat.get("/api/chat-demo/conversacion")).json()
    assert recuperado == historial


@pytest.mark.asyncio
async def test_reintento_mismo_uuid_y_datos_faltantes_generan_pedido_unico(chat, uow):
    await iniciar(chat)
    antes = await uow.valor("SELECT count(*) FROM pedido")
    cuerpo, entrada = await carrito(uow, chat)
    repetido = await chat.post("/api/chat-demo/borradores", json=cuerpo)
    assert repetido.json()["id"] == entrada
    await procesar(uow, entrada)
    assert await uow.valor("SELECT count(*) FROM pedido") == antes
    datos = await enviar(chat, "retiro, efectivo")
    await procesar(
        uow,
        datos,
        {
            "accion": "datos",
            "argumentos": {
                "tipo_entrega": "RETIRO",
                "metodo_pago": "EFECTIVO",
            },
        },
    )
    assert await uow.valor("SELECT count(*) FROM pedido") == antes + 1
    repetido = await chat.post("/api/chat-demo/borradores", json=cuerpo)
    assert repetido.json()["id"] == entrada
    assert repetido.json()["estado"] == "PROCESADO"
    assert await uow.valor("SELECT count(*) FROM pedido") == antes + 1
    cuerpo["borrador"]["items"][0]["cantidad"] = 2
    assert (await chat.post("/api/chat-demo/borradores", json=cuerpo)).status_code == 409


@pytest.mark.asyncio
async def test_no_permite_identidad_externa_referencias_ni_reordenar_pendientes(chat, uow):
    await iniciar(chat)
    _, entrada = await carrito(uow, chat)
    assert (
        await chat.post(
            "/api/chat-demo/mensajes",
            json={
                "solicitud_id": str(uuid4()),
                "texto": "consulta",
                "telefono": "5492215550987",
            },
        )
    ).status_code == 422
    assert (
        await chat.post(
            "/api/chat-demo/mensajes",
            json={
                "solicitud_id": str(uuid4()),
                "texto": "consulta",
            },
        )
    ).status_code == 409
    await procesar(uow, entrada)
    assert (
        await chat.post(
            "/api/chat-demo/mensajes",
            json={
                "solicitud_id": str(uuid4()),
                "texto": "MB-" + "A" * 43,
            },
        )
    ).status_code == 422


@pytest.mark.asyncio
async def test_archivo_ficticio_persistido_aislado_no_acredita_dinero(chat, uow):
    cookie = await iniciar(chat)
    _, entrada = await carrito(uow, chat, "TRANSFERENCIA")
    await procesar(uow, entrada)
    datos = await enviar(chat, "retiro")
    await procesar(uow, datos, {"accion": "datos", "argumentos": {"tipo_entrega": "RETIRO"}})
    contenido = b"%PDF-1.4\n% Comprobante ficticio, sin valor bancario\n%%EOF"
    solicitud = str(uuid4())
    ruta = "/api/chat-demo/comprobantes"
    headers = {"Content-Type": "application/pdf", "X-Solicitud-Id": solicitud}
    subida = await chat.post(ruta, content=contenido, headers=headers)
    assert subida.status_code == 202, subida.text
    identificador = subida.json()["id"]
    assert (await chat.post(ruta, content=contenido, headers=headers)).json()["id"] == identificador
    await procesar(uow, identificador)
    comprobante = await uow.uno(
        "SELECT * FROM whatsapp_comprobante WHERE entrada_id=%s",
        (identificador,),
    )
    assert comprobante["estado"] == "PENDIENTE"
    assert (
        await uow.valor("SELECT count(*) FROM pago WHERE pedido_id=%s", (comprobante["pedido_id"],))
        == 0
    )
    descarga = f"{ruta}/{identificador}/archivo"
    assert (await chat.get(descarga)).content == contenido
    from contextlib import asynccontextmanager

    from app.core.seguridad import crear_token
    from app.modules.whatsapp.presentation import router as interno

    @asynccontextmanager
    async def conexion_prueba():
        yield uow.conn

    # La misma bandeja interna debe descargar el archivo persistido en la demo.
    app_personal = FastAPI()
    from app.modules.usuarios.presentation.dependencias import sesion_vigente, usuario_actual
    app_personal.dependency_overrides[sesion_vigente] = usuario_actual
    app_personal.include_router(interno.router)
    from unittest.mock import patch

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_personal),
        base_url="http://prueba",
    ) as personal:
        personal.cookies.set(
            settings.cookie_sesion,
            crear_token(
                usuario_id=1,
                rol="ADMINISTRADOR",
                username="demo",
            ),
        )
        with patch.object(interno, "conexion", conexion_prueba):
            archivo_personal = await personal.get(
                f"/api/whatsapp/comprobantes/{comprobante['id']}/archivo"
            )
        assert archivo_personal.status_code == 200
        assert archivo_personal.content == contenido
    chat.cookies.clear()
    await iniciar(chat)
    assert (await chat.get(descarga)).status_code == 404
    chat.cookies.clear()
    chat.cookies.set("monu_chat_demo", cookie)
    invalido = await chat.post(
        ruta,
        content=b"<script>mal</script>",
        headers={
            "Content-Type": "image/png",
            "X-Solicitud-Id": str(uuid4()),
        },
    )
    assert invalido.status_code == 422
    assert (
        await chat.post(
            ruta,
            content=b"x" * (2 * 1024 * 1024 + 1),
            headers={
                "Content-Type": "application/pdf",
                "X-Solicitud-Id": str(uuid4()),
            },
        )
    ).status_code == 413


@pytest.mark.asyncio
async def test_demo_deshabilitada_produccion_remoto_y_csrf_no_abren_base(monkeypatch):
    from app.modules.whatsapp.presentation.router_demo import router

    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def no_conectar():
        pytest.fail("Una solicitud inválida no debe abrir conexión")

    app.dependency_overrides[obtener_uow] = no_conectar
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://prueba",
    ) as cliente:
        monkeypatch.setattr(settings, "chat_demo_habilitado", False)
        assert (await cliente.get("/api/chat-demo/config")).json()["habilitado"] is False
        assert (await cliente.post("/api/chat-demo/sesion", json={})).status_code == 403
        monkeypatch.setattr(settings, "chat_demo_habilitado", True)
        monkeypatch.setattr(settings, "entorno", "produccion")
        assert (await cliente.post("/api/chat-demo/sesion", json={})).status_code == 403
        monkeypatch.setattr(settings, "entorno", "desarrollo")
        monkeypatch.setattr(settings, "database_url", "postgresql://x:x@remoto.example/db")
        assert (await cliente.post("/api/chat-demo/sesion", json={})).status_code == 403
        monkeypatch.setattr(settings, "database_url", "postgresql://monu:monu@127.0.0.1:55439/db")
        monkeypatch.setattr(settings, "whatsapp_modo", "simulado")
        assert (await cliente.post("/api/chat-demo/sesion", json={})).status_code == 403
        assert (
            await cliente.post(
                "/api/chat-demo/sesion",
                json={},
                headers={
                    "X-Chat-Demo": "1",
                    "Origin": "https://ajeno.example",
                },
            )
        ).status_code == 403


@pytest.mark.asyncio
async def test_limite_no_impide_recuperar_intento_y_cookie_vencida_no_lee_historial(chat, uow):
    from app.modules.whatsapp.domain.mensajes import hash_referencia

    token = await iniciar(chat)
    solicitud = str(uuid4())
    entrada = await enviar(chat, "estado", solicitud)
    await procesar(uow, entrada)
    sesion = await uow.uno(
        "SELECT * FROM chat_demo_sesion WHERE token_hash=%s",
        (hash_referencia(token),),
    )
    prefijo = str(uuid4())
    await uow.ejecutar(
        """INSERT INTO whatsapp_entrada(id,telefono,texto,estado)
        SELECT %s||n,%s,'consulta','PROCESADO' FROM generate_series(1,80) n""",
        (prefijo, sesion["telefono"]),
    )
    await uow.ejecutar(
        """INSERT INTO chat_demo_operacion(sesion_hash,solicitud_id,huella,entrada_id)
        SELECT %s,md5(id)::uuid,'prueba',id FROM whatsapp_entrada
        WHERE telefono=%s AND id LIKE %s""",
        (sesion["token_hash"], sesion["telefono"], prefijo + "%"),
    )
    repetido = await chat.post(
        "/api/chat-demo/mensajes",
        json={
            "solicitud_id": solicitud,
            "texto": "estado",
        },
    )
    assert repetido.status_code == 202
    assert repetido.json()["id"] == entrada
    assert (
        await chat.post(
            "/api/chat-demo/mensajes",
            json={
                "solicitud_id": str(uuid4()),
                "texto": "estado",
            },
        )
    ).status_code == 409
    await uow.ejecutar(
        "UPDATE chat_demo_sesion SET expira_en=now()-interval '1 day' WHERE token_hash=%s",
        (sesion["token_hash"],),
    )
    assert (await chat.get("/api/chat-demo/conversacion")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("modo", ["real", "simulado"])
async def test_publicacion_compartida_requiere_autorizacion_explicita_y_conserva_cookie(
    monkeypatch, modo
):
    from app.modules.whatsapp.presentation.router_demo import router

    monkeypatch.setattr(settings, "chat_demo_habilitado", True)
    monkeypatch.setattr(settings, "chat_demo_bd_compartida_autorizada", False)
    monkeypatch.setattr(settings, "entorno", "produccion")
    monkeypatch.setattr(settings, "whatsapp_modo", modo)
    monkeypatch.setattr(settings, "database_url", "postgresql://x:x@remoto.example/demo")
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(ErrorDominio, manejador_error_dominio)

    async def no_conectar():
        pytest.fail("Sin cookie no debe abrir conexión aunque la demo pública esté autorizada")

    app.dependency_overrides[obtener_uow] = no_conectar
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://prueba",
    ) as cliente:
        assert (await cliente.get("/api/chat-demo/config")).json()["habilitado"] is False
        monkeypatch.setattr(settings, "chat_demo_bd_compartida_autorizada", True)
        assert (await cliente.get("/api/chat-demo/config")).json()["habilitado"] is True
        assert (await cliente.get("/api/chat-demo/conversacion")).status_code == 401
