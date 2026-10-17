# Backend

Seguí [AGENTS raíz](../../AGENTS.md). Consultá la sección pertinente de
[arquitectura](../../docs/ARQUITECTURA.md) y [código limpio](../../docs/CLEAN_CODE.md).

## Dónde cambiar

- `app/modules/<capacidad>/`: dominio, aplicación, SQL/adaptadores y presentación.
- `app/registro_modulos.py`: descubrimiento de `presentation/router*.py` con `router`.
- `app/main.py`: composición transversal; no registrar capacidades a mano.
- `app/core/`: configuración, pool, auditoría, seguridad y handlers HTTP.
- `app/errores.py`: excepciones compartidas sin frameworks.
- `tests/`: dominio/servicio sin base, repositorios y HTTP con PostgreSQL.

Las dependencias de negocio viven en `<capacidad>/presentation/dependencias.py`.
El dominio no importa FastAPI, Pydantic, psycopg ni `app.core`. La aplicación no
importa FastAPI, Pydantic, psycopg ni `app.core.errores`: lanza errores de
`app.errores`, y los adaptadores traducen errores del driver. Para usar otra
capacidad, llamá su fábrica pública (ej. `obtener_servicio_stock(uow)`) con la
misma unidad de trabajo. `tests/test_arquitectura.py` comprueba estas reglas.

Para código nuevo de aplicación, tomá como modelo `pedidos`, `productos`, `stock`
y `reportes`, que reciben puertos `Protocol`. `delivery`, `pagos`, `usuarios` y
`notificaciones` todavía reciben repositorios SQL concretos; no copiar ese estilo.

Reutilizá `UnidadDeTrabajo` y su alcance transaccional. Parametrizá SQL con `%s`.
Precios y estados se validan en servidor. Revisá reintentos y concurrencia al
tocar stock, pagos y caja. Declará la guarda de rol (`Sesion`, `PersonalInterno`…)
antes del servicio en la firma del endpoint, así se rechaza sin pedir conexión.
El webhook tiene validación propia. Pagos y delivery cambian el estado del pedido
con SQL propio, sin consumo de stock; ver [deuda técnica](../../docs/DEUDA_TECNICA.md).

## Verificar

Desde esta carpeta, usá `.\.venv\Scripts\python.exe` en Windows
(`.venv/bin/python` en Linux/macOS):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_arquitectura.py -q
.\.venv\Scripts\python.exe -m ruff check .
```

Elegí además los tests del comportamiento afectado. Suite completa: `-m pytest -q`,
con **PostgreSQL descartable** configurado explícitamente. Las pruebas SQL/HTTP
escriben datos; `tests/soporte_bd.py` las omite si `DATABASE_URL` no es local
(`App/.env` suele apuntar a la base compartida). No definir `MONU_PERMITIR_BD_REMOTA`.
Los skips no son aprobaciones: informarlos aparte, con su motivo (`-rs`).
Nuevas pruebas con base usan el fixture `uow` de `tests/conftest.py`.

Inicio: `.\.venv\Scripts\python.exe run.py`; en Windows no sustituirlo por
Uvicorn directo. Configuración y preparación en [desarrollo](../../docs/DESARROLLO.md).
No cambiar versiones, lint global ni migraciones para conseguir un resultado verde
en una tarea que no los necesita.
