# Backend y base de datos

Parte del **Sistema de Gestión Monu Burger** — Grupo 19, Seminario Integrador 2026.

Contiene la base de datos centralizada del sistema y la API que la consume.
El frontend vive en [`App/frontend/`](../frontend).

**Responsable:** Ignacio Pagotto (base de datos y asignación de repartidores).

## Documentación

| Documento | Para qué |
|-----------|----------|
| **[GUIA_EQUIPO.md](../../docs/GUIA_EQUIPO.md)** | Cómo conectarse a la base compartida y cómo pedir cambios de esquema. **Leer antes de empezar.** |
| **[docs/DICCIONARIO_DATOS.md](../../docs/DICCIONARIO_DATOS.md)** | Las 27 tablas con columnas, tipos, relaciones y valores permitidos. Generado del SQL. |
| **[docs/CAMBIOS_DER.md](../../docs/CAMBIOS_DER.md)** | Las 12 correcciones aplicadas al DER entregado en la Actividad N°2, y por qué. |

## Stack

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 · psycopg 3 · **SQL directo, sin ORM** |
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
.venv\Scripts\python -m uvicorn app.main:app --reload
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
│   │   ├── core/             configuración, pool de BD, errores, dependencias
│   │   ├── modules/          un subpaquete por módulo del sistema
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

# Diccionario de datos (regenerar tras cada migración nueva)
python -m scripts.diccionario

# Backend
python -m uvicorn app.main:app --reload
pytest -q
ruff check .
```

## Convenciones

- Tablas, columnas y código en **español**, `snake_case`.
- Toda consulta SQL va parametrizada (`%s`). Nunca interpolar valores.
- **Nunca editar una migración ya aplicada**: el runner detecta el cambio de
  checksum y avisa. Para cambiar el esquema, una migración nueva.
- El dominio y la aplicación no importan FastAPI ni psycopg.
- Errores de negocio: lanzar las excepciones de `app/core/errores.py`, no
  `HTTPException`.
- En endpoints con autenticación, declarar la dependencia de rol **antes** que
  `UoW` en la firma: FastAPI resuelve en orden, y así un request sin sesión se
  rechaza sin pedir conexión a la base.

## Estado

| Módulo | Estado |
|--------|--------|
| Base de datos (esquema completo) | ✅ aplicado en Supabase · 27 tablas, 3 vistas, 5 funciones, 3 triggers, 47 FKs |
| Pruebas de integridad | ✅ 27 pruebas contra la base real |
| Asignación de repartidores | 🔨 en curso |
| Pedidos · Menú · Stock · Pagos · Reportes · Bot · Usuarios | ⬜ a cargo del resto del grupo |

Las pruebas de integridad corren contra la base configurada en `DATABASE_URL`:

```bash
pytest tests/test_integridad_bd.py -v
```

Cada una corre dentro de una transacción que se revierte, así que **no ensucian
la base compartida**. Si no hay base accesible, se saltean.
