# Sistema de Gestión — Monu Burger

![CI](https://github.com/Ignapag/Proyecto---Seminario-Integrador-2026/actions/workflows/ci.yml/badge.svg)

**Grupo 19** · Seminario Integrador 2026 · Habilitación Profesional

Sistema integral de gestión para **Monu Burger**, una hamburguesería de
Ensenada, La Plata, que hoy opera sus ventas manualmente por WhatsApp e
Instagram.

El sistema digitaliza la toma de pedidos, el menú web, el control de stock por
ingrediente, la asignación de repartidores, el cierre de caja y los reportes de
ventas, con un bot de WhatsApp para notificar al cliente el estado de su pedido.

Integrantes en [INTEGRANTES.md](INTEGRANTES.md).

Para trabajar con agentes, empezar por [AGENTS.md](AGENTS.md). El
[índice técnico](docs/README.md) reúne arquitectura, código limpio, desarrollo
y uso de skills. [CLAUDE.md](CLAUDE.md) enlaza las mismas instrucciones para Claude.

## Estructura del repositorio

```
App/                    el sistema
├── frontend/           interfaz web (React + Vite)
├── backend/            API (Python + FastAPI)
├── db/                 esquema de la base de datos (SQL versionado)
├── docker-compose.yml
└── .env.example

docs/                   documentación técnica
├── README.md            índice de lectura por tarea
├── DESARROLLO.md        setup y verificaciones actuales
├── CLEAN_CODE.md        convenciones de código y revisión
├── FLUJO_IA.md          skills, roles y delegación proporcional
├── DEUDA_TECNICA.md     limitaciones conocidas con evidencia
├── GUIA_EQUIPO.md      cómo trabaja el grupo: base compartida y flujo de Git
├── ARQUITECTURA.md      estructura screaming y contrato de integración
├── DER.md              diagrama entidad-relación (generado del SQL)
├── DICCIONARIO_DATOS.md  referencia del esquema (generada del SQL)
├── CAMBIOS_DER.md      correcciones aplicadas al DER de la Actividad N°2
└── TAREAS_IGNACIO.md   plan de tareas por responsable

documentos/             entregables y documentación del proyecto
├── Actividad-02-Relevamiento-y-Alcance.pdf
├── Actividad-02-Relevamiento-y-Alcance-Reentrega.pdf
├── Informe-FODA.pdf
├── Stack-Tecnologico.pdf
├── Cronograma.pdf · Cronograma-Replanificado.mpp / .xml
├── Diagrama-PERT.pdf
└── Proyecto-Seminario-2026-Grupo-19.pdf

AGENTS.md               instrucciones comunes; también hay guías por área
CLAUDE.md               entrada a las mismas reglas desde Claude
.agents/skills/         nueve skills locales con sus recursos
.agents/skills-lock.json procedencia y hashes del traslado
.codex/agents/          cuatro roles de agente para Monu Burger
.codex/config.toml      límite de concurrencia, sin fijar modelo ni permisos
```

## Empezar a trabajar

**Leé primero [docs/GUIA_EQUIPO.md](docs/GUIA_EQUIPO.md)** y
**[docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)**: explican cómo conectarse a
la base compartida, el flujo de Git y dónde debe integrarse cada capacidad sin
crear proyectos o puntos de composición duplicados.

```bash
git clone https://github.com/Ignapag/Proyecto---Seminario-Integrador-2026.git
cd Proyecto---Seminario-Integrador-2026
git checkout -b TuNombre
```

Backend y base de datos: ver [App/backend/README.md](App/backend/README.md).

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend | React · Vite |
| Backend | Python 3.12 · FastAPI · Pydantic |
| Base de datos | PostgreSQL 16 en local/CI, Supabase para la base compartida · psycopg 3 · **SQL directo, sin ORM** |
| Autenticación | JWT en cookie HttpOnly |
| Arquitectura | Monolito modular · Screaming Architecture · Clean Architecture por capacidad |
| Servicios externos | Adaptador de Mercado Pago · integración WhatsApp Cloud API/n8n pendiente |

## Estado

La integración de las ramas quedó incorporada a `main` en `a62320c`.
Este mapa describe el código integrado, no una validación completa de producción.

| Módulo | EDT | Estado |
|--------|-----|--------|
| Base de datos | 1.9.2 | Esquema SQL versionado, migraciones y documentación generada. |
| Asignación de repartidores | 1.3.1 | Módulo delivery y endpoints integrados. |
| Pedidos | 1.2 | Creación, variantes, transiciones y conexión con stock integradas. |
| Menú web dinámico | 1.2.1 | Productos, recetas e interfaz conectada a API. |
| Control de stock | 1.5 | Ingredientes, movimientos y consumo integrados. |
| Pagos y cierre de caja | 1.4 | Efectivo, billeteras, conciliación y caja integrados; servicios externos requieren validación propia. |
| Reportes y estadísticas | 1.6 | Backend integrado; algunas vistas administrativas conservan contenido demostrativo. |
| Bot de WhatsApp (n8n) | 1.7 | Plantillas y encolado; envío simulado, integración externa pendiente. |
| Usuarios y seguridad | 1.8 | Login real, cookie JWT, roles y auditoría; sin autorregistro ni recuperación de contraseña. |

Comandos actuales en [desarrollo](docs/DESARROLLO.md) y limitaciones en
[deuda técnica](docs/DEUDA_TECNICA.md). Los resultados del informe de integración
corresponden a su fecha; no sustituyen pruebas actuales ni un CI aprobado.
