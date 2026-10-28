"""Los portales de Desarrollo pueden usar el bot sin autorizar otros sitios."""

import pytest
from starlette.requests import Request

from app.core.config import Settings, settings
from app.errores import SinPermiso
from app.modules.whatsapp.presentation.router_demo import validar_canal


@pytest.mark.parametrize(
    ("origen", "cabecera_demo", "permitido"),
    [
        ("https://monu-burger-desarrollo.pages.dev", "1", True),
        ("https://monu-burger-clientes-desarrollo.pages.dev", "1", True),
        ("https://monu-burger-clientes-desarrollo.pages.dev", "0", False),
        ("https://ajeno.pages.dev", "1", False),
        ("https://monu-burger-clientes.pages.dev", "1", False),
    ],
)
def test_origenes_del_bot_desarrollo(monkeypatch, origen, cabecera_demo, permitido):
    monkeypatch.delenv("ORIGENES_PERMITIDOS", raising=False)
    configuracion = Settings(_env_file=None)
    monkeypatch.setattr(settings, "origenes_permitidos", configuracion.origenes_permitidos)
    monkeypatch.setattr(settings, "chat_demo_habilitado", True)
    monkeypatch.setattr(settings, "chat_demo_bd_compartida_autorizada", True)
    solicitud = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "server": ("backend.example", 443),
            "path": "/api/chat-demo/sesion",
            "headers": [(b"origin", origen.encode()), (b"x-chat-demo", cabecera_demo.encode())],
            "query_string": b"",
        }
    )
    if permitido:
        assert validar_canal(solicitud) is None
    else:
        with pytest.raises(SinPermiso):
            validar_canal(solicitud)
