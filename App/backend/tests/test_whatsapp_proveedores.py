"""Contratos de proveedores sin credenciales, red real ni base de datos."""

import hashlib
import hmac
import io
import json
import logging
import re
from copy import copy
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.errores import ReglaDeNegocio
from app.modules.whatsapp.application.edicion_conversacional import resolver_items
from app.modules.whatsapp.application.servicio_bot import ServicioBot
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
                                "args": argumentos
                                if argumentos is not None
                                else {"ingrediente": "tomate"},
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
        llamadas.append((copy(solicitud), timeout))
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
        ("quiero cambiar la dirección", "preguntar", {"campo": "direccion"}),
        ("quiero cambiar la dir", "preguntar", {"campo": "direccion"}),
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
    assert datos["generationConfig"]["maxOutputTokens"] <= 768
    assert datos["generationConfig"]["candidateCount"] == 1
    assert set(datos["toolConfig"]["functionCallingConfig"]["allowedFunctionNames"]) >= {
        "datos",
        "quitar_ingrediente",
        "cantidad",
        "confirmar",
        "consulta",
        "humano",
        "preguntar",
    }
    contexto_enviado = datos["contents"][0]["parts"][0]["text"]
    assert "Doble" in contexto_enviado
    for privado in ("5492215550000", "Dirección privada", "Cliente", "Privado"):
        assert privado not in contexto_enviado


@pytest.mark.parametrize('referencia_modelo', ['Nagui burger', 'triple tasty'])
async def test_descripcion_del_catalogo_llega_desde_servicio_hasta_gemini(http, referencia_modelo):
    llamadas, respuestas = http
    producto = {
        'id': 99, 'nombre': 'Nagui burger', 'descripcion': 'Triple tasty de Nagi',
        'variantes': [], 'ingredientes_quitables': ['Lechuga', 'Tomate'],
    }

    class Repo:
        async def ingredientes_items(self, items): return []
        async def memoria(self, *args): return []

    class Productos:
        async def listar(self, **kwargs): return [producto]

    bot = ServicioBot(Repo(), None, productos=Productos())
    borrador = {
        'pedido_id': None, 'estado': 'BORRADOR', 'items': [], 'contexto_chat': {},
        'tipo_entrega': 'RETIRO', 'metodo_pago': 'EFECTIVO', 'telefono': 'privado',
        'referencia_hash': 'privado', 'version': 1,
    }
    contexto = await bot._contexto(borrador)
    assert contexto['catalogo'][0]['descripcion'] == 'Triple tasty de Nagi'
    respuestas.append(respuesta_funcion('agregar_producto', {
        'producto': referencia_modelo, 'cantidad': 1, 'aclaraciones': 'Sin lechuga',
    }))
    accion = await proveedores.GeminiInterpretador('ficticia', 'modelo').interpretar(
        'pueden agregarme una triple tasty sin lechuga porfa', contexto,
    )
    enviado = json.loads(json.loads(llamadas[0][0].data)['contents'][0]['parts'][0]['text'])
    assert enviado['contexto']['catalogo'][0]['descripcion'] == 'Triple tasty de Nagi'
    assert 'privado' not in json.dumps(enviado)
    resultado = await resolver_items(
        bot, borrador, {'id': 'ficticio'}, {'items': [], 'version': 1}, accion,
    )
    assert not isinstance(resultado, str)
    assert resultado[0] == [{
        'producto_id': 99, 'cantidad': 1, 'variante': None, 'aclaraciones': 'Sin lechuga',
    }]


@pytest.mark.parametrize('descripcion', ['x' * 500, '\U0001f354' * 500], ids=['texto', 'unicode'])
async def test_descripcion_larga_se_acota_en_la_peticion(http, descripcion):
    llamadas, respuestas = http
    respuestas.append(respuesta_funcion('consulta', {}))
    await proveedores.GeminiInterpretador('ficticia', 'modelo').interpretar('hola', {
        'catalogo': [{'id': 99, 'nombre': 'Nagui burger', 'descripcion': descripcion}],
    })
    enviado = json.loads(json.loads(llamadas[0][0].data)['contents'][0]['parts'][0]['text'])
    assert enviado['contexto']['catalogo'][0]['descripcion'] == descripcion[:200]


@pytest.mark.parametrize('descripcion', ['x' * 200, '\U0001f354' * 200], ids=['texto', 'unicode'])
async def test_catalogo_treinta_productos_ajusta_descripciones_al_presupuesto(http, descripcion):
    llamadas, respuestas = http
    respuestas.append(respuesta_funcion('consulta', {}))
    catalogo = [{
        'id': n, 'nombre': f'Burger {n}', 'descripcion': descripcion,
        'variantes': ['Simple', 'Doble', 'Triple'],
        'ingredientes': ['Pan', 'Carne', 'Cheddar', 'Lechuga', 'Tomate', 'Cebolla'],
    } for n in range(1, 31)]
    resultado = await proveedores.GeminiInterpretador('ficticia', 'modelo').interpretar(
        'quiero agregar una burger', {'catalogo': catalogo},
    )
    assert resultado == {'accion': 'consulta', 'argumentos': {}}
    entrada = json.loads(llamadas[0][0].data)['contents'][0]['parts'][0]['text']
    assert len(entrada.encode('utf-8')) <= 10000
    enviados = json.loads(entrada)['contexto']['catalogo']
    assert len(enviados) == 30
    for original, enviado in zip(catalogo, enviados, strict=True):
        assert {k: enviado[k] for k in ('id', 'nombre', 'variantes', 'ingredientes')} == {
            k: original[k] for k in ('id', 'nombre', 'variantes', 'ingredientes')
        }
        assert enviado['descripcion'] and descripcion.startswith(enviado['descripcion'])
        assert original['descripcion'] == descripcion


@pytest.mark.parametrize('descripcion', [None, 123, {'telefono': 'privado'}, ['privado']])
def test_descripcion_ausente_o_invalida_no_se_convierte_en_texto(descripcion):
    contexto = proveedores._contexto_acotado({
        'catalogo': [{'id': 99, 'nombre': 'Nagui burger', 'descripcion': descripcion}],
    })
    assert 'descripcion' not in contexto['catalogo'][0]
    assert 'privado' not in json.dumps(contexto)


async def test_descripcion_compartida_no_autoriza_elegir_un_producto_ambiguo():
    class Productos:
        async def listar(self, **kwargs):
            return [
                {'id': 99, 'nombre': 'Nagui burger', 'descripcion': 'Triple tasty'},
                {'id': 100, 'nombre': 'Otra burger', 'descripcion': 'Triple tasty'},
            ]

    bot = ServicioBot(None, None, productos=Productos())
    b = {'contexto_chat': {}, 'version': 1}
    pedido = {'items': [], 'version': 1}
    resultado = await resolver_items(bot, b, {'id': 'ficticio'}, pedido, {
        'accion': 'agregar_producto', 'argumentos': {
            'producto': 'triple tasty', 'cantidad': 1, 'aclaraciones': 'Sin lechuga',
        },
    })
    assert isinstance(resultado, str) and 'Nagui burger' in resultado and 'Otra burger' in resultado
    assert pedido['items'] == []
    assert b['contexto_chat']['edicion']['argumentos']['aclaraciones'] == 'Sin lechuga'


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
        respuesta_funcion("preguntar", {}),
        respuesta_funcion("preguntar", {"campo": "telefono"}),
        respuesta_funcion("preguntar", {"campo": "direccion", "texto": "calle privada"}),
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
    assert resultado["accion"] == "humano" and resultado["motivo"] == "PROVEEDOR"
    assert resultado["argumentos"] == {} and resultado["causa_proveedor"]
    assert len(llamadas) == 1


@pytest.mark.parametrize("error", [TimeoutError("secreto"), URLError("secreto")])
async def test_gemini_falla_cerrado_sin_reintentar(http, error):
    llamadas, respuestas = http
    respuestas.append(error)
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {})
    assert resultado == {
        "accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR",
        "causa_proveedor": "TIMEOUT" if isinstance(error, TimeoutError) else "TRANSITORIO",
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
    assert resultado == {
        "accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR",
        "causa_proveedor": "ARGUMENTOS",
    }


@pytest.mark.parametrize(
    ("campo", "texto"),
    [("direccion", "Calle 43"), ("numero", "123"), ("localidad", "Villa Elisa")],
)
async def test_simulado_usa_pregunta_pendiente_para_respuesta_corta(campo, texto):
    resultado = await proveedores.SimuladoInterpretador().interpretar(
        texto, {"conversacion": {"solicitud_pendiente": campo}}
    )
    assert resultado == {"accion": "datos", "argumentos": {campo: texto}}


async def test_simulado_pregunta_pendiente_no_sustituye_pedido_de_personal():
    resultado = await proveedores.SimuladoInterpretador().interpretar(
        "quiero hablar con una persona", {"conversacion": {"solicitud_pendiente": "direccion"}}
    )
    assert resultado == {"accion": "humano", "argumentos": {}}


def test_contexto_proyecta_solo_memoria_segura_acotada():
    contexto = {
        "estado_pedido": "CONFIRMADO",
        "tipo_entrega": "DELIVERY",
        "metodo_pago": "EFECTIVO",
        "telefono": "telefono-privado",
        "direccion": "calle-privada",
        "conversacion": {
            "solicitud_pendiente": "numero",
            "datos_presentes": [
                "direccion",
                "numero",
                "localidad",
                "referencias",
                "tipo_entrega",
                "metodo_pago",
                "telefono",
                {"secreto": "oculto"},
            ],
            "datos": {"direccion": "calle-privada"},
            "ultimos_turnos": [
                {"cliente": "turno-viejo", "asistente": "turno-viejo"},
                *[{"cliente": "c" * 300, "asistente": "a" * 500, "telefono": "telefono-privado"}]
                * 4,
            ],
        },
    }
    seguro = proveedores._contexto_acotado(contexto)
    assert seguro["estado_pedido"] == "CONFIRMADO"
    assert seguro["tipo_entrega"] == "DELIVERY" and seguro["metodo_pago"] == "EFECTIVO"
    memoria = seguro["conversacion"]
    assert memoria["solicitud_pendiente"] == "numero"
    assert memoria["datos_presentes"] == [
        "direccion",
        "numero",
        "localidad",
        "referencias",
        "tipo_entrega",
        "metodo_pago",
    ]
    assert len(memoria["ultimos_turnos"]) == 4
    assert all(
        turno == {"cliente": "c" * 240, "asistente": "a" * 400}
        for turno in memoria["ultimos_turnos"]
    )
    assert all(
        privado not in json.dumps(seguro)
        for privado in ("calle-privada", "telefono-privado", "oculto", "turno-viejo")
    )


def test_contexto_rechaza_objetos_y_enumeraciones_no_admitidas():
    seguro = proveedores._contexto_acotado(
        {
            "items": None,
            "estado_pedido": "estado-inventado",
            "tipo_entrega": "donde sea",
            "metodo_pago": {"token": "privado"},
            "conversacion": {
                "solicitud_pendiente": "telefono",
                "datos_presentes": {"direccion": "privada"},
                "ultimos_turnos": [
                    {"cliente": {"direccion": "privada"}, "asistente": ["privado"]},
                    "privado",
                ],
            },
        }
    )
    assert seguro["conversacion"] == {
        "solicitud_pendiente": None,
        "datos_presentes": [],
        "ultimos_turnos": [],
    }
    assert all(campo not in seguro for campo in ("estado_pedido", "tipo_entrega", "metodo_pago"))
    assert "privad" not in json.dumps(seguro)


async def test_gemini_pregunta_datos_faltantes_y_usa_memoria_sin_confirmar(http):
    llamadas, respuestas = http
    respuestas.append(respuesta_funcion("preguntar", {"campo": "numero"}))
    contexto = {
        "conversacion": {
            "solicitud_pendiente": "direccion",
            "datos_presentes": ["direccion"],
            "ultimos_turnos": [
                {"cliente": "Solicitó cambiar dirección", "asistente": "¿Cuál es la calle?"}
            ],
        }
    }
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar(
        "Calle 43", contexto
    )
    assert resultado == {"accion": "preguntar", "argumentos": {"campo": "numero"}}
    enviado = json.loads(llamadas[0][0].data)
    instrucciones = enviado["systemInstruction"]["parts"][0]["text"]
    assert "pregunta pendiente" in instrucciones and "historial" in instrucciones
    assert "preguntar" in instrucciones
    assert "solicitud_pendiente" in enviado["contents"][0]["parts"][0]["text"]
    respuestas.append(respuesta_funcion("confirmar", {}))
    contexto["conversacion"]["ultimos_turnos"] = [{"cliente": "confirmar", "asistente": "resumen"}]
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar(
        "sí", contexto
    )
    assert resultado["motivo"] == "PROVEEDOR"


async def test_gemini_acepta_confirmacion_explicita_solo_del_turno_actual(http):
    _, respuestas = http
    respuestas.append(respuesta_funcion("confirmar", {}))
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar(
        "confirmar",
        {
            "conversacion": {
                "solicitud_pendiente": "numero",
                "datos_presentes": [],
                "ultimos_turnos": [
                    {"cliente": "Solicitó una consulta", "asistente": "Consulta atendida"}
                ],
            }
        },
    )
    assert resultado == {"accion": "confirmar", "argumentos": {}}


@pytest.mark.parametrize("codigo", [500, 502, 503, 504])
async def test_gemini_reintenta_una_vez_error_transitorio_sin_filtrar_datos(
    http, monkeypatch, caplog, codigo
):
    llamadas, respuestas = http
    pausas = []

    async def pausa(demora):
        pausas.append(demora)

    monkeypatch.setattr(proveedores.asyncio, "sleep", pausa)
    respuestas.extend(
        [
            HTTPError(
                "https://proveedor.test/clave-secreta",
                codigo,
                "texto-privado",
                {},
                io.BytesIO(b"cuerpo-secreto"),
            ),
            respuesta_funcion("preguntar", {"campo": "direccion"}),
        ]
    )
    resultado = await proveedores.GeminiInterpretador("api-key-secreta", "modelo").interpretar(
        "mensaje-privado", {}
    )
    assert resultado == {"accion": "preguntar", "argumentos": {"campo": "direccion"}}
    assert len(llamadas) == 2 and len(pausas) == 1 and 0 < pausas[0] <= 0.5
    assert f"http={codigo}" in caplog.text and "HTTPError" in caplog.text
    assert all(
        privado not in caplog.text
        for privado in (
            "clave-secreta",
            "texto-privado",
            "cuerpo-secreto",
            "api-key-secreta",
            "mensaje-privado",
        )
    )


@pytest.mark.parametrize("codigo", [400, 401, 403, 408, 429, 501])
async def test_gemini_no_reintenta_otros_errores_http(http, codigo):
    llamadas, respuestas = http
    respuestas.append(HTTPError("https://proveedor.test", codigo, "privado", {}, None))
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {})
    assert resultado["motivo"] == "PROVEEDOR" and len(llamadas) == 1


async def test_gemini_agota_un_solo_reintento_transitorio(http, monkeypatch):
    llamadas, respuestas = http

    async def pausa(_):
        return None

    monkeypatch.setattr(proveedores.asyncio, "sleep", pausa)
    respuestas.extend(
        [HTTPError("https://proveedor.test", 503, "privado", {}, None) for _ in range(2)]
    )
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {})
    assert resultado["motivo"] == "PROVEEDOR" and len(llamadas) == 2


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


@pytest.mark.parametrize(
    ("respuesta", "causa"),
    [
        (HTTPError("https://ficticio.test", 401, "secreto", {}, None), "CREDENCIALES"),
        (HTTPError("https://ficticio.test", 403, "secreto", {}, None), "PERMISOS"),
        (HTTPError("https://ficticio.test", 429, "secreto", {}, None), "CUOTA"),
        (HTTPError("https://ficticio.test", 404, "secreto", {}, None), "MODELO"),
        (TimeoutError("secreto"), "TIMEOUT"),
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "TRUNCADA"),
        (respuesta_funcion("inventada", {}), "HERRAMIENTA"),
        (respuesta_funcion("cantidad", {"cantidad": True}), "ARGUMENTOS"),
        ({}, "RESPUESTA_INVALIDA"),
    ],
)
async def test_gemini_diagnostica_fallo_sin_registrar_datos(http, caplog, respuesta, causa):
    _, respuestas = http
    respuestas.append(respuesta)
    resultado = await proveedores.GeminiInterpretador("clave-secreta", "modelo").interpretar(
        "mensaje-privado", {}
    )
    assert resultado == {
        "accion": "humano", "argumentos": {}, "motivo": "PROVEEDOR",
        "causa_proveedor": causa,
    }
    assert causa in caplog.text
    assert all(s not in caplog.text for s in ("clave-secreta", "mensaje-privado", "secreto"))


async def test_gemini_cuota_usa_solo_alternativo_configurado_y_acota_intentos(http):
    llamadas, respuestas = http
    respuestas.extend([
        HTTPError("https://ficticio.test", 429, "privado", {}, None),
        respuesta_funcion("consulta", {}),
    ])
    resultado = await proveedores.GeminiInterpretador(
        "ficticia", "gemini-3.5-flash-lite",
        modelos_alternativos=["gemini-3.1-flash-lite"],
    ).interpretar("hola", {})
    assert resultado == {"accion": "consulta", "argumentos": {}}
    assert len(llamadas) == 2
    assert "/gemini-3.1-flash-lite:" in llamadas[1][0].full_url


async def test_gemini_no_usa_alternativo_pago_ni_reintenta_permisos(http):
    llamadas, respuestas = http
    with pytest.raises(ValueError):
        proveedores.GeminiInterpretador(
            "ficticia", "gemini-3.5-flash-lite", modelos_alternativos=["gemini-3.1-pro"]
        )
    respuestas.append(HTTPError("https://ficticio.test", 403, "privado", {}, None))
    resultado = await proveedores.GeminiInterpretador(
        "ficticia", "gemini-3.5-flash-lite",
        modelos_alternativos=["gemini-3.1-flash-lite"],
    ).interpretar("hola", {})
    assert resultado["causa_proveedor"] == "PERMISOS"
    assert len(llamadas) == 1


async def test_gemini_por_defecto_recupera_con_segundo_respaldo(http, monkeypatch):
    llamadas, respuestas = http
    respuestas.extend([
        HTTPError("https://ficticio.test", 503, "privado", {}, None),
        TimeoutError("privado"),
        respuesta_funcion("consulta", {}),
    ])
    monkeypatch.setattr(dependencias, "settings", Settings(
        _env_file=None, gemini_modo="real", gemini_api_key="ficticia",
    ))

    resultado = await dependencias.interpretador().interpretar("hola", {})

    assert resultado == {"accion": "consulta", "argumentos": {}}
    assert [solicitud.full_url.rsplit("/", 1)[-1] for solicitud, _ in llamadas] == [
        "gemini-3.5-flash-lite:generateContent",
        "gemini-3.1-flash-lite:generateContent",
        "gemini-3.6-flash:generateContent",
    ]


async def test_gemini_dos_respaldos_agotados_no_generan_cuarta_llamada(http):
    llamadas, respuestas = http
    respuestas.extend([HTTPError("https://ficticio.test", 429, "privado", {}, None)] * 3)
    resultado = await proveedores.GeminiInterpretador(
        "ficticia", "gemini-3.5-flash-lite",
        modelos_alternativos=["gemini-3.1-flash-lite", "gemini-3.6-flash"],
        max_intentos=3,
    ).interpretar("hola", {})
    assert resultado["causa_proveedor"] == "CUOTA"
    assert len(llamadas) == 3
    assert not respuestas


async def test_gemini_agota_todos_los_modelos_sin_superar_presupuesto(http):
    llamadas, respuestas = http
    respuestas.extend([HTTPError("https://ficticio.test", 429, "privado", {}, None)] * 2)
    resultado = await proveedores.GeminiInterpretador(
        "ficticia", "gemini-3.5-flash-lite",
        modelos_alternativos=["gemini-3.1-flash-lite"], max_intentos=2,
    ).interpretar("hola", {})
    assert resultado["causa_proveedor"] == "CUOTA" and len(llamadas) == 2


async def test_gemini_cada_modelo_recibe_quince_segundos_aunque_los_anteriores_agoten_plazo(
    monkeypatch, caplog,
):
    reloj = [0.0]
    llamadas = []

    def leer(solicitud, timeout):
        llamadas.append((solicitud.full_url.rsplit('/', 1)[-1], timeout))
        reloj[0] += 15
        if len(llamadas) < 3:
            raise TimeoutError('detalle-privado')
        return respuesta_funcion('consulta', {})

    monkeypatch.setattr(proveedores, 'time', SimpleNamespace(monotonic=lambda: reloj[0]))
    monkeypatch.setattr(proveedores, '_leer_json', leer)
    # Un valor heredado de Render no debe volver a recortar los respaldos.
    monkeypatch.setenv('GEMINI_TIEMPO_TOTAL', '20')
    monkeypatch.setattr(dependencias, 'settings', Settings(
        _env_file=None, gemini_modo='real', gemini_api_key='clave-privada',
    ))
    caplog.set_level(logging.INFO, logger='monuburger.whatsapp.proveedor')
    resultado = await dependencias.interpretador().interpretar('mensaje-privado', {})
    assert resultado == {'accion': 'consulta', 'argumentos': {}}
    assert llamadas == [
        ('gemini-3.5-flash-lite:generateContent', 15),
        ('gemini-3.1-flash-lite:generateContent', 15),
        ('gemini-3.6-flash:generateContent', 15),
    ]
    finales = [
        r.message for r in caplog.records if 'whatsapp_interpretacion_resultado ' in r.message
    ]
    assert len(finales) == 3
    assert all('duracion_ms=15000' in log for log in finales)
    assert 'causa=TIMEOUT' in finales[0] and 'intento=1' in finales[0]
    assert 'causa=TIMEOUT' in finales[1] and 'intento=2' in finales[1]
    assert 'causa=OK' in finales[2] and 'intento=3' in finales[2]
    referencias = re.findall(r'referencia=([a-f0-9]{12})', caplog.text)
    assert referencias and len(set(referencias)) == 1
    assert all(
        s not in caplog.text for s in ('clave-privada', 'mensaje-privado', 'detalle-privado')
    )


async def test_gemini_timeout_por_intento_avanza_y_agota_respaldos_sin_colgarse(monkeypatch):
    import asyncio
    import time

    llamadas = []

    async def red_lenta(funcion, solicitud, timeout):
        llamadas.append(solicitud.full_url)
        await asyncio.Event().wait()

    monkeypatch.setattr(proveedores.asyncio, 'to_thread', red_lenta)
    inicio = time.monotonic()
    resultado = await proveedores.GeminiInterpretador(
        'ficticia', 'gemini-3.5-flash-lite', timeout=0.01,
        modelos_alternativos=['gemini-3.1-flash-lite', 'gemini-3.6-flash'], max_intentos=3,
    ).interpretar('hola', {})
    assert resultado['causa_proveedor'] == 'TIMEOUT'
    assert len(llamadas) == 3 and len(set(llamadas)) == 3
    assert time.monotonic() - inicio < 1


@pytest.mark.parametrize('respuesta', [
    {}, {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
    respuesta_funcion('cantidad', {'cantidad': True}),
    respuesta_funcion('confirmar', {}),
])
async def test_gemini_respuesta_invalida_prueba_respaldo_sin_aplicar_salida_anterior(
    http, respuesta,
):
    llamadas, respuestas = http
    respuestas.extend([respuesta, respuesta_funcion('consulta', {})])
    resultado = await proveedores.GeminiInterpretador(
        'ficticia', 'gemini-3.5-flash-lite', modelos_alternativos=['gemini-3.1-flash-lite'],
    ).interpretar('hola', {})
    assert resultado == {'accion': 'consulta', 'argumentos': {}}
    assert len(llamadas) == 2


async def test_gemini_cancelacion_no_inicia_otro_modelo(monkeypatch):
    import asyncio

    iniciado = asyncio.Event()
    llamadas = []

    async def red_lenta(funcion, solicitud, timeout):
        llamadas.append(solicitud.full_url)
        iniciado.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(proveedores.asyncio, 'to_thread', red_lenta)
    tarea = asyncio.create_task(proveedores.GeminiInterpretador(
        'ficticia', 'gemini-3.5-flash-lite', modelos_alternativos=['gemini-3.1-flash-lite'],
    ).interpretar('hola', {}))
    await iniciado.wait()
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    assert len(llamadas) == 1


async def test_gemini_respuesta_tardia_no_sustituye_respaldo_ni_muta_peticion(monkeypatch):
    import asyncio
    import threading

    liberar = threading.Event()
    terminado = threading.Event()
    peticiones = []

    def leer(solicitud, timeout):
        peticiones.append(solicitud)
        if len(peticiones) == 1:
            try:
                liberar.wait(1)
                return respuesta_funcion('cancelar', {})
            finally:
                terminado.set()
        liberar.set()
        return respuesta_funcion('consulta', {})

    monkeypatch.setattr(proveedores, '_leer_json', leer)
    try:
        resultado = await proveedores.GeminiInterpretador(
            'ficticia', 'gemini-3.5-flash-lite', timeout=0.02,
            modelos_alternativos=['gemini-3.1-flash-lite'],
        ).interpretar('hola', {})
        assert await asyncio.to_thread(terminado.wait, 1)
        assert resultado == {'accion': 'consulta', 'argumentos': {}}
        assert len(peticiones) == 2 and peticiones[0] is not peticiones[1]
        assert peticiones[0].full_url.endswith('/gemini-3.5-flash-lite:generateContent')
        assert peticiones[1].full_url.endswith('/gemini-3.1-flash-lite:generateContent')
    finally:
        liberar.set()


def test_contexto_catalogo_y_edicion_no_envian_datos_personales():
    seguro = proveedores._contexto_acotado({
        "catalogo": [{"id": 7, "nombre": "Crispy", "variantes": ["Simple", "Doble"],
                      "ingredientes": ["bacon"], "direccion": "privado"}] * 200,
        "edicion_pendiente": {"accion": "cantidad", "argumentos": {
            "producto": "Crispy", "cantidad": 1, "aclaraciones": "sin bacon",
            "direccion": "privado", "telefono": "privado"}},
    })
    assert 0 < len(seguro["catalogo"]) <= 30
    assert seguro["catalogo"][0] == {
        "id": 7, "nombre": "Crispy", "variantes": ["Simple", "Doble"],
        "ingredientes": ["bacon"],
    }
    assert seguro["edicion_pendiente"]["argumentos"]["producto"] == "Crispy"
    assert "privado" not in json.dumps(seguro)


async def test_gemini_contexto_excesivo_diagnostica_sin_llamar(http):
    llamadas, _ = http
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar(
        "hola", {"catalogo": [{"id": 1, "nombre": "a" * 80,
                                "variantes": ["v" * 80] * 10,
                                "ingredientes": ["i" * 60] * 20}] * 30}
    )
    assert resultado["causa_proveedor"] == "CONTEXTO"
    assert not llamadas


async def test_gemini_diagnostico_http_tambien_respeta_timeout_del_intento(http, monkeypatch):
    _, respuestas = http
    respuestas.append(HTTPError("https://ficticio.test", 400, "privado", {}, None))

    def cuerpo_lento(error):
        import time
        time.sleep(0.2)
        return "CREDENCIALES"

    monkeypatch.setattr(proveedores, "_causa_http_gemini", cuerpo_lento)
    resultado = await proveedores.GeminiInterpretador(
        "ficticia", "modelo", timeout=0.01
    ).interpretar("hola", {})
    assert resultado["causa_proveedor"] == "TIMEOUT"


@pytest.mark.parametrize('codigo', [400, 401, 403])
async def test_gemini_http_no_recuperable_corta_aunque_diagnostico_se_demore(
    http, monkeypatch, codigo, caplog,
):
    import time

    llamadas, respuestas = http
    respuestas.extend([
        HTTPError('https://ficticio.test', codigo, 'privado', {}, None),
        respuesta_funcion('consulta', {}),
    ])

    def diagnostico_lento(error):
        time.sleep(0.1)
        return 'CREDENCIALES'

    monkeypatch.setattr(proveedores, '_causa_http_gemini', diagnostico_lento)
    resultado = await proveedores.GeminiInterpretador(
        'ficticia', 'gemini-3.5-flash-lite', timeout=0.01,
        modelos_alternativos=['gemini-3.1-flash-lite'],
    ).interpretar('hola', {})
    assert resultado['motivo'] == 'PROVEEDOR'
    assert len(llamadas) == 1
    assert f'http={codigo}' in caplog.text


async def test_gemini_clave_invalida_en_http400_no_se_confunde_con_herramienta(http):
    _, respuestas = http
    respuestas.append(HTTPError("https://ficticio.test", 400, "privado", {}, io.BytesIO(
        b'{"error":{"details":[{"reason":"API_KEY_INVALID","message":"secreto"}]}}'
    )))
    resultado = await proveedores.GeminiInterpretador("ficticia", "modelo").interpretar("hola", {})
    assert resultado["causa_proveedor"] == "CREDENCIALES"


def test_contexto_edicion_ignora_accion_sin_tipo_valido():
    assert "edicion_pendiente" not in proveedores._contexto_acotado({
        "edicion_pendiente": {"accion": {}, "argumentos": {"direccion": "privado"}},
    })


@pytest.mark.parametrize("config", [
    {"gemini_modelos_alternativos": ["gemini-3.1-pro"]},
    {"gemini_max_intentos": 4}, {"gemini_timeout": 0}, {"gemini_timeout": 31},
])
def test_configuracion_rechaza_alternativos_y_presupuestos_no_permitidos(config):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **config)


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
        (b"[]", None),
        (b"no-json token-secreto", None),
        (b"x" * 32769, None),
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
