"""Contratos de proveedores sin credenciales, red real ni base de datos."""

import hashlib
import hmac
import io
import json
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.errores import ReglaDeNegocio
from app.modules.whatsapp.infrastructure import proveedores
from app.modules.whatsapp.presentation import dependencias


def respuesta_funcion(nombre="quitar_ingrediente", argumentos=None):
    return {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": nombre,
                                "args": argumentos or {"ingrediente": "tomate"},
                            },
                        }
                    ]
                },
            }
        ]
    }


@pytest.fixture
def http(monkeypatch):
    llamadas = []
    respuestas = []

    def abrir(solicitud, *, timeout):
        llamadas.append((solicitud, timeout))
        respuesta = respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        if isinstance(respuesta, tuple):
            cuerpo, cabeceras = respuesta
        else:
            cuerpo, cabeceras = json.dumps(respuesta).encode(), {}
        archivo = io.BytesIO(cuerpo)
        archivo.headers = cabeceras
        return archivo

    monkeypatch.setattr(proveedores._HTTP, "open", abrir)
    return llamadas, respuestas


@pytest.mark.parametrize(
    ("texto", "accion", "argumentos"),
    [
        ("¿Le podés sacar el tomate?", "quitar_ingrediente", {"ingrediente": "tomate"}),
        ("sin tomate", "quitar_ingrediente", {"ingrediente": "tomate"}),
        (
            "quitar tomate del ítem 2",
            "quitar_ingrediente",
            {"ingrediente": "tomate", "item_indice": 2},
        ),
        ("cantidad: 3", "cantidad", {"cantidad": 3}),
        ("ítem 2 cantidad 4", "cantidad", {"cantidad": 4, "item_indice": 2}),
        ("confirmar", "confirmar", {}),
        ("no confirmar", "humano", {}),
        ("cantidad: 0", "humano", {}),
        ("retiro y efectivo", "datos", {"tipo_entrega": "retiro", "metodo_pago": "efectivo"}),
        ("transferencia", "datos", {"metodo_pago": "transferencia"}),
        (
            "dirección: Calle 43; número: 123; localidad: Ensenada",
            "datos",
            {
                "direccion": "Calle 43",
                "numero": "123",
                "localidad": "Ensenada",
            },
        ),
        ("¿cuál es el estado?", "consulta", {}),
        ("quiero hablar con una persona", "humano", {}),
    ],
)
async def test_simulador_devuelve_intenciones_sin_inventar_producto(texto, accion, argumentos):
    resultado = await proveedores.SimuladoInterpretador().interpretar(texto, {"items": [{}, {}]})
    assert resultado == {"accion": accion, "argumentos": argumentos}


@pytest.mark.parametrize(
    "texto",
    [
        "cantidad: 2.5",
        "cantidad: 2,5",
        "sin tomate; cantidad: 4",
        "ítem 1 cantidad 2; ítem 2 cantidad 3",
        "sin tomate y sin cebolla",
    ],
)
async def test_simulador_no_aplica_parcialmente_operaciones_compuestas(texto):
    resultado = await proveedores.SimuladoInterpretador().interpretar(texto, {})
    assert resultado == {"accion": "humano", "argumentos": {}}


async def test_direccion_no_cambia_modalidad_por_contener_retiro_o_efectivo():
    resultado = await proveedores.SimuladoInterpretador().interpretar(
        "dirección: Pasaje del Retiro; referencias: cartel Efectivo",
        {},
    )
    assert resultado == {
        "accion": "datos",
        "argumentos": {
            "direccion": "Pasaje del Retiro",
            "referencias": "cartel Efectivo",
        },
    }


async def test_pregunta_sobre_pago_no_se_convierte_en_eleccion():
    resultado = await proveedores.SimuladoInterpretador().interpretar("¿aceptan efectivo?", {})
    assert resultado["accion"] in {"consulta", "humano"}


async def test_gemini_solo_pide_una_accion_y_omite_contexto_personal(http):
    llamadas, respuestas = http
    respuestas.append(respuesta_funcion())
    resultado = await proveedores.GeminiInterpretador(
        "clave-ficticia", "gemini-3.1-flash-lite"
    ).interpretar(
        "sin tomate",
        {
            "telefono": "5492215550000",
            "direccion": "Dirección privada",
            "nombre": "Cliente",
            "items": [
                {
                    "item_indice": 1,
                    "nombre": "Doble",
                    "cantidad": 2,
                    "variante": "Grande",
                    "ingredientes": ["tomate"],
                    "cliente": "Privado",
                }
            ],
        },
    )
    assert resultado == {"accion": "quitar_ingrediente", "argumentos": {"ingrediente": "tomate"}}
    assert len(llamadas) == 1
    solicitud, timeout = llamadas[0]
    assert timeout == 15
    assert solicitud.full_url.endswith("/models/gemini-3.1-flash-lite:generateContent")
    assert "clave-ficticia" not in solicitud.full_url
    datos = json.loads(solicitud.data)
    assert datos["generationConfig"]["maxOutputTokens"] <= 256
    assert datos["generationConfig"]["candidateCount"] == 1
    assert set(datos["toolConfig"]["functionCallingConfig"]["allowedFunctionNames"]) == {
        "datos",
        "quitar_ingrediente",
        "cantidad",
        "confirmar",
        "consulta",
        "humano",
    }
    contexto_enviado = datos["contents"][0]["parts"][0]["text"]
    assert "Doble" in contexto_enviado
    for privado in ("5492215550000", "Dirección privada", "Cliente", "Privado"):
        assert privado not in contexto_enviado


@pytest.mark.parametrize(
    "respuesta",
    [
        {},
        {"candidates": []},
        {"candidates": [{}]},
        respuesta_funcion("pagar", {"monto": 1}),
        respuesta_funcion("cantidad", {"cantidad": True}),
        respuesta_funcion("cantidad", {"cantidad": 51}),
        respuesta_funcion("cantidad", {"cantidad": 2, "precio": 1}),
        respuesta_funcion("datos", {"metodo_pago": "gratis"}),
        respuesta_funcion("datos", {"direccion": "x" * 301}),
        {"candidates": [{"content": {"parts": [{"text": "Confirmado y pagado"}]}}]},
        {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {
                        "parts": [
                            {
                                "functionCall": {"name": "confirmar", "args": {}},
                            }
                        ]
                    },
                }
            ]
        },
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"functionCall": {"name": "confirmar", "args": {}}},
                            {"functionCall": {"name": "consulta", "args": {}}},
                        ]
                    }
                }
            ]
        },
        {
            "candidates": [
                {"content": {"parts": [{"functionCall": {"name": "consulta", "args": {}}}]}},
                {"content": {"parts": [{"functionCall": {"name": "confirmar", "args": {}}}]}},
            ]
        },
    ],
)
async def test_gemini_deriva_salidas_no_validas_sin_reintentar(http, respuesta):
    llamadas, respuestas = http
    respuestas.append(respuesta)
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar(
        "confirmar", {}
    )
    assert resultado == {"accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR"}
    assert len(llamadas) == 1


@pytest.mark.parametrize("error", [TimeoutError("secreto"), URLError("secreto")])
async def test_gemini_falla_cerrado_sin_reintentar(http, error):
    llamadas, respuestas = http
    respuestas.append(error)
    assert await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {}) == {
        "accion": "humano",
        "argumentos": {},
        "motivo": "PROVEEDOR",
    }
    assert len(llamadas) == 1


async def test_gemini_no_inventa_confirmacion_a_partir_del_modelo(http):
    _, respuestas = http
    respuestas.append(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {"name": "confirmar", "args": {}},
                            }
                        ]
                    }
                }
            ]
        }
    )
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {})
    assert resultado == {"accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR"}


async def test_gemini_acota_contexto_y_rechaza_mensaje_excesivo(http):
    llamadas, respuestas = http
    respuestas.append(respuesta_funcion())
    interpretador = proveedores.GeminiInterpretador("ficticia", "modelo")
    await interpretador.interpretar("sin tomate", {"items": [{"nombre": "x" * 2000}] * 1000})
    assert len(llamadas[0][0].data) < 12000
    assert await interpretador.interpretar("x" * 2001, {}) == {
        "accion": "humano",
        "argumentos": {},
        "motivo": "MENSAJE_LARGO",
    }
    assert len(llamadas) == 1


async def test_cloud_envia_texto_y_devuelve_id_aceptado_no_entregado(http):
    llamadas, respuestas = http
    respuestas.append({"messages": [{"id": "wamid.ejemplo"}]})
    transporte = proveedores.WhatsAppCloud("token-ficticio", "123456", "v24.0", timeout=7)
    assert await transporte.enviar("5492215550000", "Pedido recibido") == "wamid.ejemplo"
    solicitud, timeout = llamadas[0]
    assert timeout == 7
    assert solicitud.full_url == "https://graph.facebook.com/v24.0/123456/messages"
    assert solicitud.get_header("Authorization") == "Bearer token-ficticio"
    assert json.loads(solicitud.data) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "5492215550000",
        "type": "text",
        "text": {"preview_url": False, "body": "Pedido recibido"},
    }


@pytest.mark.parametrize(
    ("telefono", "destino"),
    [
        ("5492215550000", "542215550000"),
        ("5492215550001", "5492215550001"),
        ("34600123456", "34600123456"),
    ],
)
async def test_destinatarios_prueba_solo_adaptan_el_numero_configurado(
    http, monkeypatch, telefono, destino
):
    llamadas, respuestas = http
    respuestas.append({"messages": [{"id": "wamid.prueba"}]})
    monkeypatch.setenv("WHATSAPP_DESTINATARIOS_PRUEBA_SIN_9", '["5492215550000"]')
    configuracion = Settings(
        _env_file=None,
        whatsapp_modo="real",
        whatsapp_token="token-ficticio",
        whatsapp_phone_number_id="123456",
    )
    monkeypatch.setattr(dependencias, "settings", configuracion)

    assert await dependencias.transporte().enviar(telefono, "Pedido recibido") == "wamid.prueba"
    assert json.loads(llamadas[0][0].data)["to"] == destino
    assert len(llamadas) == 1


@pytest.mark.parametrize("numero", ["542215550000", "+5492215550000", "549123", "34600123456"])
def test_destinatarios_prueba_rechazan_formato_ajeno_al_caso_argentino(monkeypatch, numero):
    monkeypatch.setenv("WHATSAPP_DESTINATARIOS_PRUEBA_SIN_9", json.dumps([numero]))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("codigo", "tipo_error"),
    [
        (400, ReglaDeNegocio),
        (500, proveedores.ErrorEnvioIncierto),
        (408, proveedores.ErrorEnvioIncierto),
    ],
)
async def test_cloud_distingue_rechazo_de_resultado_incierto(http, codigo, tipo_error):
    llamadas, respuestas = http
    respuestas.append(HTTPError("https://graph.facebook.com", codigo, "token-secreto", {}, None))
    with pytest.raises(tipo_error, match="WhatsApp") as error:
        await proveedores.WhatsAppCloud("token", "123", "v24.0").enviar("5492215550000", "hola")
    assert "token-secreto" not in str(error.value)
    assert len(llamadas) == 1


@pytest.mark.parametrize(
    ("cuerpo", "codigo_meta"),
    [
        (b'{"error":{"code":131030,"message":"token-secreto"}}', 131030),
        (b'{"error":{"code":190,"message":"token-secreto"}}', 190),
        (b'{"error":{"code":"token-secreto"}}', None),
        (b'{"error":{"code":true}}', None),
        (b'[]', None),
        (b'no-json token-secreto', None),
        (b'x' * 32769, None),
    ],
    ids=["no-permitido", "token", "codigo-texto", "codigo-bool", "lista", "no-json", "excesivo"],
)
async def test_cloud_informa_codigo_http_sin_filtrar_datos_del_proveedor(
    http, caplog, cuerpo, codigo_meta
):
    llamadas, respuestas = http
    respuestas.append(
        HTTPError("https://graph.facebook.com", 400, "token-secreto", {}, io.BytesIO(cuerpo))
    )
    transporte = proveedores.WhatsAppCloud(
        "token-secreto", "123", "v24.0", destinatarios_prueba_sin_9=["5492215550000"]
    )
    with pytest.raises(ReglaDeNegocio):
        await transporte.enviar("5492215550000", "mensaje-privado")
    registros = [r for r in caplog.records if r.name == "monuburger.whatsapp.proveedor"]
    assert len(registros) == 1
    assert registros[0].args[:3] == (400, codigo_meta, True)
    assert "token-secreto" not in caplog.text
    assert "mensaje-privado" not in caplog.text
    assert "5492215550000" not in caplog.text
    assert len(llamadas) == 1


async def test_cloud_diagnostico_distingue_credenciales_y_conserva_contexto_real(http, caplog):
    _, respuestas = http
    for token in ("token-ficticio-a", "token-ficticio-b", "token-ficticio-a"):
        respuestas.append(HTTPError("https://graph.facebook.com", 403, "rechazo", {}, None))
        with pytest.raises(ReglaDeNegocio):
            await proveedores.WhatsAppCloud(token, "123456", "v26.0").enviar(
                "5492215550000", "mensaje-privado"
            )
    registros = [r for r in caplog.records if r.name == "monuburger.whatsapp.proveedor"]
    assert len(registros) == 3
    assert all(len(r.args) == 8 for r in registros)
    huellas = [r.args[3] for r in registros]
    assert huellas[0] == huellas[2] and huellas[0] != huellas[1]
    assert all(len(h) == 16 and all(c in "0123456789abcdef" for c in h) for h in huellas)
    assert all(r.args[4:6] == ("123456", "v26.0") for r in registros)
    assert len({r.args[6] for r in registros}) == 1
    assert "token-ficticio" not in caplog.text
    assert "mensaje-privado" not in caplog.text
    assert "5492215550000" not in caplog.text


@pytest.mark.parametrize(
    "respuesta",
    [TimeoutError("token-secreto"), {}, {"messages": []}, (b"x" * 32769, {}), (b"no-json", {})],
)
async def test_cloud_no_afirma_fallo_reintentable_tras_respuesta_desconocida(http, respuesta):
    llamadas, respuestas = http
    respuestas.append(respuesta)
    with pytest.raises(proveedores.ErrorEnvioIncierto):
        await proveedores.WhatsAppCloud("token", "123", "v24.0").enviar("5492215550000", "hola")
    assert len(llamadas) == 1


@pytest.mark.parametrize(
    ("telefono", "texto"), [("../otra-ruta", "hola"), ("5492215550000", "x" * 4097)]
)
async def test_cloud_no_hace_red_para_entrada_invalida(http, telefono, texto):
    llamadas, _ = http
    with pytest.raises(ReglaDeNegocio):
        await proveedores.WhatsAppCloud("token", "123", "v24.0").enviar(telefono, texto)
    assert not llamadas


async def test_simulacion_es_distinguible_del_envio_real():
    transporte = proveedores.SimuladoTransporte()
    primero = await transporte.enviar("5492215550000", "hola")
    segundo = await transporte.enviar("5492215550000", "hola")
    assert primero.startswith("sim-") and segundo.startswith("sim-")
    assert primero != segundo


def test_firma_valida_cuerpo_exacto_y_rechaza_manipulacion():
    cuerpo = b'{"entry":[]}'
    firma = "sha256=" + hmac.new(b"secreto-ficticio", cuerpo, hashlib.sha256).hexdigest()
    assert proveedores.validar_firma(cuerpo, firma, "secreto-ficticio")
    assert not proveedores.validar_firma(cuerpo + b" ", firma, "secreto-ficticio")
    assert not proveedores.validar_firma(cuerpo, firma, "otra-clave")


@pytest.mark.parametrize("firma", [None, "", "sha1=abc", "sha256=abc", "sha256=" + "é" * 64])
def test_firma_invalida_se_rechaza_sin_error(firma):
    assert not proveedores.validar_firma(b"cuerpo", firma, "secreto")
    assert not proveedores.validar_firma(b"cuerpo", firma, "")


async def test_descarga_autenticada_sin_persistir_comprobante(http):
    llamadas, respuestas = http
    respuestas.extend(
        [
            {
                "url": "https://lookaside.fbsbx.com/whatsapp_business/adjunto",
                "mime_type": "image/png",
                "file_size": 8,
            },
            (b"imagen12", {"Content-Type": "image/png"}),
        ]
    )
    contenido, tipo = await proveedores.WhatsAppCloud("token", "123", "v24.0").bajar_comprobante(
        "456"
    )
    assert (contenido, tipo) == (b"imagen12", "image/png")
    assert len(llamadas) == 2
    assert all(s.get_header("Authorization") == "Bearer token" for s, _ in llamadas)
    assert llamadas[0][0].full_url == "https://graph.facebook.com/v24.0/456"


@pytest.mark.parametrize(
    "url",
    [
        "http://lookaside.fbsbx.com/a",
        "https://evil.test/a",
        "https://lookaside.fbsbx.com.evil.test/a",
        "https://fbcdn.net/a",
        "https://usuario@lookaside.fbsbx.com/a",
        "https://lookaside.fbsbx.com:8443/a",
    ],
)
async def test_descarga_no_envia_token_a_hosts_no_permitidos(http, url):
    llamadas, respuestas = http
    respuestas.append({"url": url, "mime_type": "image/png", "file_size": 1})
    with pytest.raises(ReglaDeNegocio):
        await proveedores.WhatsAppCloud("token", "123", "v24.0").bajar_comprobante("456")
    assert len(llamadas) == 1


@pytest.mark.parametrize(
    "metadatos",
    [
        {"mime_type": "image/svg+xml", "file_size": 1},
        {"mime_type": "image/png", "file_size": 5242881},
    ],
)
async def test_descarga_rechaza_tipo_y_tamano_antes_de_bajar(http, metadatos):
    llamadas, respuestas = http
    respuestas.append({"url": "https://lookaside.fbsbx.com/a", **metadatos})
    with pytest.raises(ReglaDeNegocio):
        await proveedores.WhatsAppCloud("token", "123", "v24.0").bajar_comprobante("456")
    assert len(llamadas) == 1


@pytest.mark.parametrize(
    ("contenido", "tipo"),
    [(b"x" * 5242881, "image/png"), (b"abc", "text/html")],
    ids=["excesivo", "tipo-distinto"],
)
async def test_descarga_valida_contenido_aunque_metadatos_mientan(http, contenido, tipo):
    _, respuestas = http
    respuestas.extend(
        [
            {"url": "https://lookaside.fbsbx.com/a", "mime_type": "image/png", "file_size": 1},
            (contenido, {"Content-Type": tipo}),
        ]
    )
    with pytest.raises(ReglaDeNegocio):
        await proveedores.WhatsAppCloud("token", "123", "v24.0").bajar_comprobante("456")


def test_no_sigue_redirecciones_que_puedan_filtrar_credenciales():
    from urllib.request import Request

    solicitud = Request("https://lookaside.fbsbx.com/a", headers={"Authorization": "Bearer token"})
    assert (
        proveedores._SinRedirecciones().redirect_request(
            solicitud,
            None,
            302,
            "Found",
            {},
            "https://evil.test/",
        )
        is None
    )
