"""Pruebas del algoritmo de agrupacion y asignacion (tareas 9 y 10).

Logica pura: no necesitan base de datos.

Las coordenadas son reales de la zona de reparto de Monu Burger.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.modules.delivery.domain.entidades import (
    GrupoDeReparto,
    PedidoParaDespachar,
    RepartidorDisponible,
    agrupar_pedidos,
    distancia_km,
    elegir_repartidor,
    planificar,
)

BASE = datetime(2026, 9, 11, 20, 0)

# Zonas del relevamiento
ENSENADA, EL_DIQUE, PUNTA_LARA = 1, 2, 3


def pedido(
    id_: int,
    *,
    lat: float | None = -34.860,
    lng: float | None = -57.907,
    zona: int | None = ENSENADA,
    minutos: int = 0,
) -> PedidoParaDespachar:
    return PedidoParaDespachar(
        pedido_id=id_,
        numero=1000 + id_,
        zona_id=zona,
        zona_nombre="Ensenada" if zona == ENSENADA else "Otra",
        lat=lat,
        lng=lng,
        creado_en=BASE + timedelta(minutes=minutos),
    )


def repartidor(id_: int, *, lat: float | None = -34.860, lng: float | None = -57.907):
    return RepartidorDisponible(repartidor_id=id_, nombre=f"Repartidor {id_}", lat=lat, lng=lng)


# ---------------------------------------------------------------- distancia

def test_distancia_entre_dos_puntos_conocidos():
    """Ensenada centro a La Plata centro: unos 6-7 km en linea recta."""
    d = distancia_km(-34.860, -57.907, -34.921, -57.954)
    assert 5 < d < 12


def test_distancia_de_un_punto_a_si_mismo_es_cero():
    assert distancia_km(-34.86, -57.90, -34.86, -57.90) == 0


def test_distancia_es_simetrica():
    ida = distancia_km(-34.860, -57.907, -34.870, -57.920)
    vuelta = distancia_km(-34.870, -57.920, -34.860, -57.907)
    assert ida == vuelta


# ---------------------------------------------- tarea 9: agrupacion

def test_dos_pedidos_cercanos_de_la_misma_zona_van_juntos():
    a = pedido(1, lat=-34.860, lng=-57.907)
    b = pedido(2, lat=-34.862, lng=-57.909)  # ~300 m

    grupos = agrupar_pedidos([a, b], radio_km=1.5)

    assert len(grupos) == 1
    assert grupos[0].cantidad == 2


def test_dos_pedidos_lejanos_salen_por_separado():
    a = pedido(1, lat=-34.860, lng=-57.907)
    b = pedido(2, lat=-34.884, lng=-57.935)  # ~3,5 km

    grupos = agrupar_pedidos([a, b], radio_km=1.5)

    assert len(grupos) == 2
    assert all(g.cantidad == 1 for g in grupos)


def test_pedidos_de_zonas_distintas_no_se_agrupan_aunque_esten_cerca():
    """Dos puntos pueden estar cerca en linea recta y lejos en la calle:
    el arroyo y la autopista separan zonas."""
    a = pedido(1, lat=-34.860, lng=-57.907, zona=ENSENADA)
    b = pedido(2, lat=-34.861, lng=-57.908, zona=EL_DIQUE)  # ~150 m

    grupos = agrupar_pedidos([a, b], radio_km=1.5)

    assert len(grupos) == 2


def test_nunca_mas_de_dos_pedidos_por_viaje():
    """Regla del negocio: cada repartidor sale con hasta 2 pedidos."""
    pedidos = [pedido(i, lat=-34.860 + i * 0.0001, lng=-57.907) for i in range(1, 6)]

    grupos = agrupar_pedidos(pedidos, radio_km=1.5, max_por_viaje=2)

    assert all(g.cantidad <= 2 for g in grupos)
    assert sum(g.cantidad for g in grupos) == 5


def test_no_se_pierde_ni_se_duplica_ningun_pedido():
    pedidos = [
        pedido(1, lat=-34.860, lng=-57.907),
        pedido(2, lat=-34.861, lng=-57.908),
        pedido(3, lat=-34.884, lng=-57.935),
        pedido(4, zona=PUNTA_LARA, lat=-34.820, lng=-57.958),
    ]

    grupos = agrupar_pedidos(pedidos, radio_km=1.5)

    ids = sorted(p.pedido_id for g in grupos for p in g.pedidos)
    assert ids == [1, 2, 3, 4]


def test_el_pedido_mas_antiguo_encabeza_el_primer_grupo():
    """Sin esta prioridad, un pedido viejo puede quedar postergado."""
    viejo = pedido(1, minutos=0, lat=-34.880, lng=-57.930)
    nuevo_a = pedido(2, minutos=30, lat=-34.860, lng=-57.907)
    nuevo_b = pedido(3, minutos=31, lat=-34.861, lng=-57.908)

    grupos = agrupar_pedidos([nuevo_a, nuevo_b, viejo], radio_km=1.5)

    assert grupos[0].pedidos[0].pedido_id == 1


def test_elige_al_vecino_mas_cercano_no_al_primero_que_encuentra():
    ancla = pedido(1, lat=-34.860, lng=-57.907, minutos=0)
    lejano = pedido(2, lat=-34.868, lng=-57.915, minutos=1)   # ~1,1 km
    cercano = pedido(3, lat=-34.8605, lng=-57.9075, minutos=2)  # ~70 m

    grupos = agrupar_pedidos([ancla, lejano, cercano], radio_km=1.5)

    assert {p.pedido_id for p in grupos[0].pedidos} == {1, 3}


def test_pedido_sin_coordenadas_sale_solo():
    """Sin ubicacion no hay forma de saber si esta cerca de otro."""
    con_ubicacion = pedido(1, lat=-34.860, lng=-57.907)
    sin_ubicacion = pedido(2, lat=None, lng=None)

    grupos = agrupar_pedidos([con_ubicacion, sin_ubicacion], radio_km=1.5)

    assert len(grupos) == 2


def test_pedido_sin_zona_resuelta_sale_solo():
    a = pedido(1, lat=-34.860, lng=-57.907, zona=ENSENADA)
    b = pedido(2, lat=-34.861, lng=-57.908, zona=None)

    grupos = agrupar_pedidos([a, b], radio_km=1.5)

    assert len(grupos) == 2


def test_sin_pedidos_no_hay_grupos():
    assert agrupar_pedidos([], radio_km=1.5) == []


def test_max_por_viaje_invalido_es_error():
    with pytest.raises(ValueError):
        agrupar_pedidos([pedido(1)], radio_km=1.5, max_por_viaje=0)


# ------------------------------------------- tarea 10: asignacion

def test_elige_al_repartidor_mas_cercano():
    grupo = GrupoDeReparto(pedidos=[pedido(1, lat=-34.860, lng=-57.907)])
    lejos = repartidor(1, lat=-34.900, lng=-57.950)
    cerca = repartidor(2, lat=-34.861, lng=-57.908)

    assert elegir_repartidor(grupo, [lejos, cerca]).repartidor_id == 2


def test_sin_repartidores_no_asigna():
    grupo = GrupoDeReparto(pedidos=[pedido(1)])
    assert elegir_repartidor(grupo, []) is None


def test_respeta_el_radio_de_busqueda():
    grupo = GrupoDeReparto(pedidos=[pedido(1, lat=-34.860, lng=-57.907)])
    muy_lejos = repartidor(1, lat=-34.600, lng=-58.380)  # Buenos Aires

    assert elegir_repartidor(grupo, [muy_lejos], radio_busqueda_km=10) is None


def test_usa_repartidor_sin_ubicacion_si_ninguno_tiene():
    """Mejor despachar con un criterio debil que dejar el pedido sin asignar."""
    grupo = GrupoDeReparto(pedidos=[pedido(1)])
    sin_gps = repartidor(1, lat=None, lng=None)

    assert elegir_repartidor(grupo, [sin_gps]).repartidor_id == 1


def test_ante_empate_elige_el_de_menor_id():
    """La asignacion tiene que ser determinista y repetible."""
    grupo = GrupoDeReparto(pedidos=[pedido(1, lat=-34.860, lng=-57.907)])
    a = repartidor(7, lat=-34.861, lng=-57.908)
    b = repartidor(3, lat=-34.861, lng=-57.908)

    assert elegir_repartidor(grupo, [a, b]).repartidor_id == 3


# ------------------------------------------------ planificacion completa

def test_planificar_asigna_un_repartidor_distinto_a_cada_viaje():
    pedidos = [
        pedido(1, lat=-34.860, lng=-57.907, minutos=0),
        pedido(2, lat=-34.884, lng=-57.935, minutos=1),
    ]
    repartidores = [
        repartidor(1, lat=-34.860, lng=-57.907),
        repartidor(2, lat=-34.884, lng=-57.935),
    ]

    propuestas = planificar(pedidos, repartidores, radio_agrupacion_km=1.5)

    assert len(propuestas) == 2
    asignados = [p.repartidor.repartidor_id for p in propuestas if p.asignable]
    assert len(set(asignados)) == 2, "un repartidor no puede estar en dos viajes"


def test_planificar_deja_sin_asignar_si_faltan_repartidores():
    pedidos = [
        pedido(1, lat=-34.860, lng=-57.907, minutos=0),
        pedido(2, lat=-34.884, lng=-57.935, minutos=1),
    ]

    propuestas = planificar(pedidos, [repartidor(1)], radio_agrupacion_km=1.5)

    assert sum(1 for p in propuestas if p.asignable) == 1
    assert sum(1 for p in propuestas if not p.asignable) == 1


def test_planificar_informa_la_distancia_al_primer_domicilio():
    pedidos = [pedido(1, lat=-34.860, lng=-57.907)]
    propuestas = planificar(
        pedidos, [repartidor(1, lat=-34.870, lng=-57.920)], radio_agrupacion_km=1.5
    )

    assert propuestas[0].distancia_km is not None
    assert propuestas[0].distancia_km > 0


def test_un_pedido_listo_sale_solo_sin_esperar():
    """Decision acordada: agrupar es una optimizacion, no una condicion."""
    propuestas = planificar([pedido(1)], [repartidor(1)], radio_agrupacion_km=1.5)

    assert len(propuestas) == 1
    assert propuestas[0].grupo.cantidad == 1
    assert propuestas[0].asignable
