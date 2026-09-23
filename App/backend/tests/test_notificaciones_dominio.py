"""Pruebas de dominio del modulo de Notificaciones / Bot de WhatsApp.

Logica pura: renderizado de plantillas y el catalogo de eventos. No
necesitan base de datos.
"""

from __future__ import annotations

from app.modules.notificaciones.domain.entidades import (
    EventoNotificacion,
    renderizar_plantilla,
)

# Debe coincidir con el CHECK plantilla_clave_chk de la migracion 006.
CLAVES_EN_LA_MIGRACION = {
    "BIENVENIDA",
    "PEDIDO_CONFIRMADO",
    "EN_CAMINO",
    "ENTREGADO",
    "ALERTA_STOCK",
    "CIERRE_CAJA",
}


def test_eventos_coinciden_con_el_check_de_la_base():
    """Si alguien agrega un evento aca sin migrar la base (o viceversa), esto
    lo detecta antes que un INSERT fallando en produccion."""
    assert {evento.value for evento in EventoNotificacion} == CLAVES_EN_LA_MIGRACION


def test_renderiza_las_variables_de_la_plantilla_de_bienvenida():
    """Mismo texto y variable que App/db/seed.sql."""
    cuerpo = "Hola! Bienvenido a Monu Burger. Para hacer tu pedido entra a {{url_menu}}."
    resultado = renderizar_plantilla(cuerpo, {"url_menu": "https://monuburger.com.ar"})
    assert resultado == "Hola! Bienvenido a Monu Burger. Para hacer tu pedido entra a https://monuburger.com.ar."


def test_renderiza_varias_variables_en_el_mismo_cuerpo():
    cuerpo = "Tu pedido #{{numero_pedido}} ya salio con {{repartidor}}."
    resultado = renderizar_plantilla(cuerpo, {"numero_pedido": "1042", "repartidor": "Marcos"})
    assert resultado == "Tu pedido #1042 ya salio con Marcos."


def test_variable_faltante_queda_visible_en_vez_de_fallar():
    cuerpo = "Recibimos tu pedido #{{numero_pedido}} por ${{total}}."
    resultado = renderizar_plantilla(cuerpo, {"numero_pedido": "1042"})
    assert resultado == "Recibimos tu pedido #1042 por ${{total}}."


def test_sin_variables_devuelve_el_cuerpo_tal_cual():
    cuerpo = "Mensaje fijo sin placeholders."
    assert renderizar_plantilla(cuerpo, {}) == cuerpo
