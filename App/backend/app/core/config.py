"""Configuracion de la aplicacion, leida de variables de entorno / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Aplicacion ---------------------------------------------------
    app_nombre: str = "Monu Burger API"
    entorno: str = Field(default="desarrollo")
    debug: bool = True

    # --- Base de datos ------------------------------------------------
    database_url: str = "postgresql://monu:monu@localhost:5432/monuburger"
    db_pool_min: int = 1
    db_pool_max: int = 10
    # Segundos a esperar por una conexion libre antes de responder 503.
    db_timeout_conexion: float = 5.0

    # --- CORS ---------------------------------------------------------
    # El frontend lo desarrolla otro integrante; este origen es el puerto
    # por defecto de Vite, para cuando se integre.
    origenes_permitidos: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Billeteras virtuales / Mercado Pago --------------------------
    mp_access_token: str | None = None
    mp_webhook_secret: str | None = None
    mp_url_notificacion: str = "https://api.monuburger.local/api/pagos/webhook/mercadopago"
    mp_url_retorno: str = "http://localhost:5173/pago/resultado"

    # Nota: la configuracion de JWT y cookies vive en el modulo de Usuarios y
    # Seguridad (EDT 1.8), a cargo de otro integrante.

    @field_validator("origenes_permitidos", mode="before")
    @classmethod
    def _parsear_origenes(cls, valor: object) -> object:
        if isinstance(valor, str):
            return [item.strip() for item in valor.split(",") if item.strip()]
        return valor

    @property
    def es_produccion(self) -> bool:
        return self.entorno.lower() in {"produccion", "production", "prod"}

    @property
    def dsn_visible(self) -> str:
        """DSN sin credenciales, apto para logs."""
        sin_esquema = self.database_url.split("://", 1)[-1]
        if "@" in sin_esquema:
            sin_esquema = sin_esquema.split("@", 1)[1]
        return sin_esquema


@lru_cache
def obtener_settings() -> Settings:
    return Settings()


settings = obtener_settings()
