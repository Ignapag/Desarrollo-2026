# Sistema de Gestión — Monu Burger

**Grupo 19** · Seminario Integrador 2026 · Habilitación Profesional

Sistema integral de gestión para **Monu Burger**, una hamburguesería de
Ensenada, La Plata, que hoy opera sus ventas manualmente por WhatsApp e
Instagram.

El sistema digitaliza la toma de pedidos, el menú web, el control de stock por
ingrediente, la asignación de repartidores, el cierre de caja y los reportes de
ventas, con un bot de WhatsApp para notificar al cliente el estado de su pedido.

Integrantes en [INTEGRANTES.md](INTEGRANTES.md).

## Estructura del repositorio

```
App/                    el sistema
├── frontend/           interfaz web (React + Vite)
├── backend/            API (Python + FastAPI)
├── db/                 esquema de la base de datos (SQL versionado)
├── docker-compose.yml
└── .env.example

docs/                   documentación técnica
├── GUIA_EQUIPO.md      cómo trabaja el grupo: base compartida y flujo de Git
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
```

## Empezar a trabajar

**Leé primero [docs/GUIA_EQUIPO.md](docs/GUIA_EQUIPO.md)**: explica cómo
conectarse a la base de datos compartida, qué no hacer nunca con ella, y el
flujo de trabajo con Git (rama propia + Pull Request).

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
| Base de datos | PostgreSQL 17 (Supabase) · psycopg 3 · **SQL directo, sin ORM** |
| Autenticación | JWT en cookie HttpOnly |
| Arquitectura | Monolito modular · Clean Architecture |
| Servicios externos | n8n · WhatsApp Cloud API · OpenStreetMap + Leaflet |

## Estado

| Módulo | EDT | Estado |
|--------|-----|--------|
| Base de datos | 1.9.2 | ✅ esquema aplicado y verificado · 27 tablas, 27 pruebas de integridad |
| Asignación de repartidores | 1.3.1 | 🔨 en curso |
| Pedidos | 1.2 | ⬜ |
| Menú web dinámico | 1.2.1 | 🔨 en curso |
| Control de stock | 1.5 | ⬜ |
| Pagos y cierre de caja | 1.4 | ⬜ |
| Reportes y estadísticas | 1.6 | ⬜ |
| Bot de WhatsApp (n8n) | 1.7 | ⬜ |
| Usuarios y seguridad | 1.8 | ⬜ |
