# Backend y base de datos

Parte del **Sistema de Gestión Monu Burger** — Grupo 19, Seminario Integrador 2026.

Contiene la base de datos centralizada del sistema y la API que la consume.
El frontend vive en [`App/frontend/`](../frontend).

Agentes: leer [AGENTS.md](AGENTS.md). Setup y verificaciones actuales en
[DESARROLLO.md](../../docs/DESARROLLO.md); arquitectura y código limpio en el
[índice técnico](../../docs/README.md).

**Responsable:** Ignacio Pagotto (base de datos y asignación de repartidores).

## Documentación

| Documento | Para qué |
|-----------|----------|
| **[GUIA_EQUIPO.md](../../docs/GUIA_EQUIPO.md)** | Cómo conectarse a la base compartida y cómo pedir cambios de esquema. **Leer antes de empezar.** |
| **[docs/DER.md](../../docs/DER.md)** | Diagrama entidad-relación del esquema implementado. Generado del SQL, se renderiza en GitHub. |
| **[docs/DICCIONARIO_DATOS.md](../../docs/DICCIONARIO_DATOS.md)** | Tablas con columnas, tipos, relaciones y valores permitidos. Generado del SQL. |
| **[docs/CAMBIOS_DER.md](../../docs/CAMBIOS_DER.md)** | Correcciones aplicadas al DER entregado en la Actividad N°2, y por qué. |

## Stack

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 en local/CI; base compartida en Supabase · psycopg 3 · **SQL directo, sin ORM** |
| Backend | Python 3.12 · FastAPI · Pydantic |
| Arquitectura | Monolito modular · Clean Architecture |
| Administración de BD | DBeaver Community |

## Puesta en marcha

El grupo comparte **una sola base en la nube**. Pedí la cadena de conexión y
armá tu `.env`:

```bash
cd App
cp .env.example .env      # completar DATABASE_URL con sslmode=require
```

```bash
cd App/backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m scripts.migrate --status    # ver estado del esquema
.venv\Scripts\python run.py
```

| Servicio | URL |
|----------|-----|
| API | http://localhost:8000 |
| Documentación (Swagger) | http://localhost:8000/docs |
| Healthcheck | http://localhost:8000/api/salud |

Si `/api/salud` responde `degradado`, no estás llegando a la base.

Para trabajar con una base **local** en vez de la compartida (recomendado para
experimentar), apuntá `DATABASE_URL` a `localhost` y levantala con Docker:

```bash
cd App
docker compose up -d db
```

## Estructura

```
App/
├── db/
│   ├── migrations/           migraciones .sql versionadas
│   └── seed.sql              datos de desarrollo
├── backend/
│   ├── app/
│   │   ├── core/             configuración, BD y piezas transversales
│   │   ├── modules/          capacidades de negocio (arquitectura screaming)
│   │   ├── registro_modulos.py  composición automática de routers
│   │   └── main.py
│   ├── scripts/
│   │   ├── migrate.py        ejecutor de migraciones
│   │   └── diccionario.py    generador del diccionario de datos
│   └── tests/
├── docker-compose.yml        postgres + backend (+ n8n opcional)
└── .env.example
```

## Comandos

```bash
# Migraciones (desde App/backend/)
python -m scripts.migrate              # aplicar pendientes
python -m scripts.migrate --status     # ver qué falta
python -m scripts.migrate --seed       # aplicar + datos de desarrollo
python -m scripts.migrate --reset      # DESTRUCTIVO, bloqueado contra la base compartida

# Documentación del esquema (regenerar tras cada migración nueva)
python -m scripts.diccionario
python -m scripts.der

# Backend  (usar run.py, NO uvicorn directo: ver nota abajo)
python run.py
pytest -q
ruff check .
```

## Nota para Windows

Levantá la API con **`python run.py`**, no con `uvicorn app.main:app`.

En Windows, psycopg en modo async necesita `SelectorEventLoop` y Python usa
`ProactorEventLoop` por defecto. Ajustarlo dentro de la aplicación no alcanza:
cuando uvicorn importa `app.main`, el event loop ya está creado. `run.py` fija
la política antes de arrancar uvicorn.

Si la levantás con uvicorn directo, la API responde pero **ninguna consulta a
PostgreSQL funciona**: todos los endpoints devuelven 503 y `/api/salud` informa
`degradado`.

## Convenciones

- Tablas, columnas y código en **español**, `snake_case`.
- Toda consulta SQL va parametrizada (`%s`). Nunca interpolar valores.
- **Nunca editar una migración ya aplicada**: el runner detecta el cambio de
  checksum y avisa. Para cambiar el esquema, una migración nueva.
- El dominio y la aplicación no importan FastAPI, Pydantic ni psycopg
  (`tests/test_arquitectura.py` lo comprueba).
- Cada capacidad conserva dominio, aplicación, infraestructura y presentación
  dentro de `app/modules/<capacidad>/`.
- Los routers `presentation/router*.py` se descubren automáticamente: no
  agregar imports de módulos a `app/main.py`.
- Las dependencias específicas viven en la presentación de su capacidad, no
  en `app/core/dependencias.py`.
- Errores de negocio: lanzar las excepciones de `app/errores.py`, no
  `HTTPException`. `app/core/errores.py` solo las traduce a HTTP.
- En endpoints con autenticación, declarar la dependencia de rol **antes** que
  `UoW` en la firma: FastAPI resuelve en orden, y así un request sin sesión se
  rechaza sin pedir conexión a la base.

## Estado

| Módulo | Estado |
|--------|--------|
| Base de datos | Diez migraciones SQL versionadas y seed; comprobar el destino y su estado antes de aplicar. |
| Pruebas | Suite pytest de dominio, servicios, arquitectura, repositorios y HTTP. Requiere base descartable para los casos SQL/HTTP. |
| Asignación de repartidores | Agrupación, asignación y ciclo de entrega integrados. |
| Usuarios y seguridad | Login, hash, cookie JWT, roles y auditoría; sin endpoints de autorregistro o recuperación. |
| Notificaciones / Bot de WhatsApp | Plantillas y encolado; adaptador de envío simulado. |
| Pedidos · Productos · Stock · Pagos · Reportes | Módulos integrados en `app/modules/`; revisar pruebas y contratos de la capacidad afectada. |

La documentación anterior de integración conserva resultados de su fecha.
Limitaciones conocidas en [DEUDA_TECNICA.md](../../docs/DEUDA_TECNICA.md).

Las pruebas SQL/HTTP (integridad, repositorios, concurrencia, HTTP) escriben en
la base: algunas revierten su transacción y otras confirman y limpian. Solo
corren si `DATABASE_URL` es local (`localhost`, `127.0.0.1`, `::1`, socket Unix o el
servicio `db`);
con el `.env` de la base compartida se **omiten** y `pytest -rs` muestra el motivo.
Cómo levantar una base descartable para la suite completa: ver
[DESARROLLO.md](../../docs/DESARROLLO.md).
