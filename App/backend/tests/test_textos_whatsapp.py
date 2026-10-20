"""Presentación de pedidos por WhatsApp: pruebas puras, sin base ni proveedor."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.whatsapp.domain.conversacion import elegir_conversacion, pregunta_pedido
from app.modules.whatsapp.domain.textos import (
    INICIO_WEB,
    dinero,
    estado_pedido,
    instrucciones_pago,
    mensaje_web,
    resultado_transferencia,
    resumen_pedido,
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(12000, "$ 12.000"), (Decimal("12000.50"), "$ 12.000,50"), ("1234.995", "$ 1.235")],
)
def test_importes_en_pesos_argentinos(valor, esperado):
    assert dinero(valor) == esperado


def _pedido():
    return {
        "id": "id-interno-no-publico",
        "numero": 37,
        "items": [{"cantidad": 2, "nombre_producto": "Monu doble", "aclaraciones": "sin cebolla"}],
        "total": Decimal("24000.50"),
        "tipo_entrega": "RETIRO",
        "estado": "LISTO",
    }


def test_resumen_muestra_notas_e_importe_sin_identificadores():
    texto = resumen_pedido(_pedido())
    assert "*Tu pedido*" in texto
    assert "2 × Monu doble" in texto and "sin cebolla" in texto
    assert "$ 24.000,50" in texto and "Retiro en el local" in texto
    assert "id-interno" not in texto and "37" not in texto


def _carrito():
    return {
        "items": [
            {"producto_id": 987, "cantidad": 2, "variante": "Doble", "aclaraciones": "sin cebolla"}
        ],
        "contacto": {"nombre": "Ana", "apellido": "Pérez", "telefono": "5492215551234"},
        "tipo_entrega": "DELIVERY",
        "metodo_pago": "TRANSFERENCIA",
        "direccion_nueva": {
            "calle": "Calle 7",
            "numero": "100",
            "localidad": "La Plata",
            "referencia": "Timbre A",
        },
    }


PRODUCTOS = [
    {
        "id": 987,
        "nombre": "Monu",
        "precio_base": "8000",
        "variantes": [{"nombre": "Doble", "precio": "12000.50"}],
    }
]


def test_mensaje_web_legible_valorado_en_servidor_sin_identificadores():
    datos = _carrito()
    datos["precio"] = 1
    texto = mensaje_web(datos, PRODUCTOS, datetime(2026, 10, 17, 2, 3, 4, tzinfo=UTC))
    assert texto.startswith(INICIO_WEB)
    assert "2 × Monu (Doble) — $ 24.001" in texto
    assert "sin cebolla" in texto and "Ana Pérez" in texto
    assert "Delivery" in texto and "transferencia" in texto
    assert "Calle 7 100, La Plata" in texto and "Timbre A" in texto
    assert "16/10/2026 a las 23:03:04" in texto
    assert "$ 24.001" in texto and "envío se confirma aparte" in texto
    assert all(
        valor not in texto for valor in ("987", "5492215551234", "MB-", "token", "referencia_hash")
    )


def test_retiro_no_incluye_direccion_y_no_se_trunca_mensaje_largo():
    datos = _carrito()
    datos["tipo_entrega"] = "RETIRO"
    texto = mensaje_web(datos, PRODUCTOS, datetime.now(UTC))
    assert "Calle 7" not in texto
    datos["items"][0]["aclaraciones"] = "a" * 4100
    with pytest.raises(ValueError, match="límite de WhatsApp"):
        mensaje_web(datos, PRODUCTOS, datetime.now(UTC))


def test_estado_listo_respeta_modalidad_sin_prometer_horario():
    pedido = _pedido()
    assert "retirarlo" in estado_pedido(pedido)
    assert "camino" not in estado_pedido(pedido)
    pedido["tipo_entrega"] = "DELIVERY"
    assert "esperando salir a reparto" in estado_pedido(pedido)
    assert "va en camino" not in estado_pedido(pedido)


def test_retiro_en_estado_en_camino_sigue_listo_para_retirar():
    texto = estado_pedido({**_pedido(), "estado": "EN_CAMINO"})
    assert "sigue listo para retirar" in texto
    assert "camino" not in texto and "reparto" not in texto


@pytest.mark.parametrize(
    "estado", ["PENDIENTE", "CONFIRMADO", "EN_PREPARACION", "LISTO", "EN_CAMINO",
               "ENTREGADO", "CANCELADO", "DESCONOCIDO"]
)
def test_estado_no_expone_codigo_tecnico_ni_identificadores(estado):
    pedido = {**_pedido(), "estado": estado}
    texto = estado_pedido(pedido)
    assert "37" not in texto and "id-interno" not in texto and estado not in texto


@pytest.mark.parametrize("estado", ["PENDIENTE", "CONFIRMADO", "EN_PREPARACION"])
def test_estado_habitual_es_breve_y_no_repite_publicidad(estado):
    texto = estado_pedido({**_pedido(), "estado": estado})
    assert len(texto) <= 60
    assert "Monu Burger" not in texto


def test_efectivo_no_pide_comprobante_y_transferencia_requiere_revision():
    retiro = instrucciones_pago("EFECTIVO", "", "RETIRO")
    entrega = instrucciones_pago("EFECTIVO", "", "DELIVERY")
    assert "retires" in retiro and "recibas" in entrega
    assert "comprobante" not in retiro + entrega
    transferencia = instrucciones_pago("TRANSFERENCIA", "Alias: monu.burger", "RETIRO")
    assert "Alias: monu.burger" in transferencia
    assert "comprobante" in transferencia and "empleado" in transferencia
    assert "va a revisar" in transferencia
    assert "Pedinos por este chat" in instrucciones_pago("TRANSFERENCIA", "", "RETIRO")


def test_resultado_pago_distingue_aprobacion_y_pide_proximo_paso():
    aprobacion = resultado_transferencia(37, True)
    assert "Pago confirmado" in aprobacion and "37" not in aprobacion
    rechazo = resultado_transferencia(37, False)
    assert "37" not in rechazo and "No pudimos aprobar" in rechazo
    assert "mandanos el comprobante correcto" in rechazo


def test_lista_identifica_compras_por_opcion_y_producto_sin_numero_pedido():
    opciones = [
        {"numero": 987654, "descripcion": "2 × Cheese", "referencia_hash": "interno-a"},
        {"numero": 876543, "descripcion": "1 × Bacon", "referencia_hash": "interno-b"},
        {"numero": None, "descripcion": "1 × Monu", "referencia_hash": "interno-c"},
    ]
    texto = pregunta_pedido(opciones)
    assert "1." in texto and "2." in texto and "3." in texto
    assert "2 × Cheese" in texto and "1 × Bacon" in texto
    assert "987654" not in texto and "876543" not in texto and "interno-" not in texto
    assert elegir_conversacion("2", opciones) is opciones[1]
    assert elegir_conversacion("pedido #987654", opciones) is opciones[0]
