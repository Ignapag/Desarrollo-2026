"""La guarda de pruebas con base solo acepta destinos locales o un opt-in explicito."""

from __future__ import annotations

import pytest

from app.core.config import settings
from tests.soporte_bd import VARIABLE_PERMITIR_REMOTA, motivo_para_omitir_bd


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://monu:monu@localhost:5432/monuburger",
        "postgresql://monu:monu@127.0.0.1:55432/monuburger",
        "postgresql://monu:monu@db:5432/monuburger",
        "host=/var/run/postgresql dbname=monuburger",
    ],
)
def test_acepta_bases_locales(monkeypatch: pytest.MonkeyPatch, dsn: str) -> None:
    _sin_variables_de_conexion(monkeypatch)
    monkeypatch.setattr(settings, "database_url", dsn)
    assert motivo_para_omitir_bd() is None


@pytest.mark.parametrize(
    ("dsn", "entorno"),
    [
        ("postgresql://u@localhost/x?hostaddr=203.0.113.5", {}),
        ("postgresql:///x", {"PGHOST": "remota.example"}),
        ("postgresql:///x", {"PGHOSTADDR": "203.0.113.5"}),
        ("postgresql://u@localhost/x?service=remoto", {}),
        ("postgresql:///x", {"PGSERVICE": "remoto"}),
    ],
)
def test_omite_destinos_remotos_indirectos(
    monkeypatch: pytest.MonkeyPatch, dsn: str, entorno: dict[str, str]
) -> None:
    _sin_variables_de_conexion(monkeypatch)
    for variable, valor in entorno.items():
        monkeypatch.setenv(variable, valor)
    monkeypatch.setattr(settings, "database_url", dsn)
    assert motivo_para_omitir_bd() is not None


def _sin_variables_de_conexion(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (VARIABLE_PERMITIR_REMOTA, "PGHOST", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(variable, raising=False)


def test_omite_una_base_remota_sin_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _sin_variables_de_conexion(monkeypatch)
    monkeypatch.setattr(
        settings, "database_url", "postgresql://u:clave@aws-0.pooler.supabase.com:5432/postgres"
    )
    motivo = motivo_para_omitir_bd()
    assert motivo is not None
    assert "aws-0.pooler.supabase.com" in motivo
    assert "clave" not in motivo


def test_el_opt_in_explicito_permite_una_base_remota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VARIABLE_PERMITIR_REMOTA, "1")
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@remota.example:5432/x")
    assert motivo_para_omitir_bd() is None
