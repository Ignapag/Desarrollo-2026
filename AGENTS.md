# Monu Burger: instrucciones para agentes

Sistema de gestión de una hamburguesería, Grupo 19 del Seminario Integrador 2026.
Monolito modular: React/Vite en `App/frontend`, Python/FastAPI en `App/backend`
y PostgreSQL con SQL directo en `App/db`. Respondé en español.

## Antes de trabajar

1. Revisá `git status --short --branch` y el diff existente; conservá trabajo ajeno.
2. Leé las instrucciones del área y solo las referencias que requiera la tarea.
3. Buscá con `rg` primero en el área afectada; ampliá por sus consumidores.
4. Contrastá documentación con código, configuración y pruebas. Diferenciá estado
   actual, deuda y propuestas. No trates un informe histórico como verificación nueva.

Las instrucciones explícitas del usuario prevalecen sobre las convenciones del
proyecto. Respetá el alcance pedido y la autorización ya dada. Preguntá solo por
decisiones bloqueantes; resolvé los detalles locales con el código y las guías.

## Mapa y lectura dirigida

| Trabajo | Carpeta | Referencia |
| --- | --- | --- |
| API, reglas, roles, SQL de repositorios | `App/backend` | [AGENTS backend](App/backend/AGENTS.md) |
| Pantallas, estado, llamadas del navegador | `App/frontend` | [AGENTS frontend](App/frontend/AGENTS.md) |
| Esquema, migraciones y seed | `App/db` | [AGENTS SQL](App/db/AGENTS.md) |
| Guías técnicas | `docs` | [AGENTS docs](docs/AGENTS.md) y [índice](docs/README.md) |
| Límites y flujos del sistema | Áreas afectadas | [Arquitectura](docs/ARQUITECTURA.md) |
| Estados, cobros, reparto y correcciones | `pedidos`, `stock`, `pagos`, `delivery`, WhatsApp y panel | [Operación de pedidos](docs/OPERACION_PEDIDOS.md) |
| Convenciones del código | Archivos afectados | [Código limpio](docs/CLEAN_CODE.md) |
| Setup, comandos y CI | Paquete afectado | [Desarrollo](docs/DESARROLLO.md) |
| Skills, roles y delegación | `.agents`, `.codex` | [Flujo de IA](docs/FLUJO_IA.md) |

No cargar todas las guías, skills, migraciones, PDFs, imágenes, dependencias ni
historiales por defecto. No editar artefactos generados para corregir sus fuentes.

## Flujo proporcional

- **Consulta/revisión:** investigar y responder; no convertirla en implementación.
- **Cambio chico:** inspección dirigida, implementación y comprobación de lo afectado.
  Sin planes persistidos, subagentes, cambios de rama o commits por rutina.
- **Cambio mediano:** plan breve en conversación, contratos y pruebas pertinentes.
  Revisión independiente si el riesgo la justifica y la sesión permite delegar.
- **Cambio grande:** etapas con criterios verificables. Delegá subtareas independientes
  cuando aporten, con objetivo y archivos asignados; coordiná contratos e integración.
- **Bug:** reproducir o demostrar la causa antes de corregir; verificar la regresión.
- No repetir lecturas, auditorías o suites aprobadas sin cambios o evidencia nueva.
- No agregar pantallas, avisos, dependencias, refactors ni infraestructura ajenos
  al objetivo. Las mejoras fuera de alcance se proponen, no se implementan solas.
- No crear commits, cambiar de rama, hacer push o publicar salvo que la tarea lo
  requiera o el usuario lo pida. Una instrucción de skill no amplía esa autorización.

## Invariantes del proyecto

- Un único frontend en `App/frontend` y una aplicación FastAPI.
- Backend por capacidad: `domain`, `application`, `infrastructure`, `presentation`.
  `core` no importa capacidades; sus factories viven en la presentación del módulo.
- Publicar routers como `router` en `presentation/router*.py`; el registro es automático.
- Dominio sin frameworks ni infraestructura; aplicación sin FastAPI, Pydantic ni psycopg.
  Los errores viven en `app.errores`. Otra capacidad se usa por su aplicación o su
  fábrica pública en `presentation/dependencias.py`, nunca por su `infrastructure`.
- SQL parametrizado con `%s`, sin ORM ni consultas interpoladas con entradas del usuario.
- Preservar transacciones de pedido/stock/pagos y reglas de reintentos/concurrencia.
  La API decide precios, stock, transiciones y permisos; el navegador no es autoridad.
- JWT en cookie HttpOnly; mantener el cliente HTTP y la validación backend de roles.
- Migraciones aplicadas inmutables; agregar una nueva y regenerar documentación SQL.
  Cambios en base compartida siguen [la coordinación del equipo](docs/GUIA_EQUIPO.md).
- Tests, seeds y experimentos usan una base descartable configurada explícitamente.
  `App/.env` suele apuntar a la base compartida: pytest omite las pruebas SQL/HTTP
  si `DATABASE_URL` no es local. No definir `MONU_PERMITIR_BD_REMOTA` en tareas de
  agentes. No aplicar migraciones ni limpiar datos en la nube como preparación rutinaria.
- Nunca copiar secretos de `.env`, cookies o proveedores a logs, documentos ni `VITE_*`.
- No afirmar que registro, recuperación, analítica demostrativa o notificaciones
  simuladas son integraciones completas. Límites en [deuda técnica](docs/DEUDA_TECNICA.md).

## Skills y agentes

Las 9 skills locales y sus recursos están en `.agents/skills/<nombre>/SKILL.md`.
Elegí las pertinentes y leé sus instrucciones antes de aplicarlas; no ejecutar
todas por cada tarea ni reinstalarlas por rutina. Usá la versión **local** de
`prompt` para Monu Burger, aunque una global del mismo nombre mencione RivalFut.
El inventario, procedencia y skills globales se explican en [flujo IA](docs/FLUJO_IA.md).

**Todo trabajo sobre el frontend debe utilizar `ui-ux-pro-max`**, incluido
análisis, diseño, implementación, refactor, corrección y revisión. Antes de
trabajar, leé la [skill local](.agents/skills/ui-ux-pro-max/SKILL.md) y aplicá las
guías pertinentes al cambio: accesibilidad, interacción, responsive, componentes,
tipografía, color y patrones del stack React/Tailwind existente. Conservá la
identidad visual de Monu Burger y el alcance pedido; usar la skill no implica
rediseñar pantallas ni generar un sistema visual nuevo para cada ajuste.

Los roles `monu_explorer`, `monu_implementer`, `monu_reviewer` y `monu_architect`
están en `.codex/agents`. Heredan modelo, esfuerzo y permisos de la sesión.
La configuración limita a tres subagentes o el límite menor de la herramienta.
No delegar tareas triviales ni editar los mismos archivos desde dos agentes.
El agente principal comprueba el diff y la evidencia antes de integrar.

## Verificar y entregar

Comandos desde el paquete correspondiente, con dependencias ya preparadas:

- Backend en Windows: `.\.venv\Scripts\python.exe -m pytest <tests-afectados> -q`
  y `.\.venv\Scripts\python.exe -m ruff check <archivos-afectados>`.
- Composición backend: incluir `tests/test_arquitectura.py`.
- Frontend: `npm run lint` y `npm run build` (el código de `src/` es JSX).
- Documentación/configuración: enlaces, rutas, sintaxis y diff; no requiere arrancar la app.
- Raíz: `git diff --check` y revisión del diff/status final.

Suite completa, base descartable y pasos de CI en [desarrollo](docs/DESARROLLO.md).
No hay script `npm test`. Informá aprobadas y omitidas por separado; build no
demuestra funcionamiento en navegador ni CI verde. No modificar reglas o pruebas
para ocultar deuda heredada.

Al entregar: qué cambió, por qué, verificaciones ejecutadas y limitaciones reales.
Actualizar solo la documentación dueña de los contratos o comandos que cambiaron.
