# Desarrollo y verificaciones

Comandos para PowerShell, salvo los bloques identificados como shell de CI.
Ejecutar desde la carpeta indicada. Python 3.12+ y Node 22 con npm; usar el lockfile
existente. No introducir pnpm, Prisma, Redis ni comandos del stack de RivalFut.

## Preparar dependencias

Desde la raíz, copiar el ejemplo solo si no existe la configuración local:

```powershell
if (-not (Test-Path -LiteralPath 'App/.env')) {
    Copy-Item -LiteralPath 'App/.env.example' -Destination 'App/.env'
}
```

Completarlo localmente sin imprimir secretos. No sustituir un `.env` existente.
Desde `App/backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Usar el entorno existente si ya está preparado. No hace falta activarlo:
los ejemplos invocan su intérprete directamente. En Linux/macOS su ruta es
`.venv/bin/python`. Desde `App/frontend`:

```powershell
npm ci
```

`npm ci` reemplaza dependencias instaladas; usarlo al preparar o actualizar el
entorno, no antes de cada comprobación si el lockfile y las dependencias no cambiaron.

## Base local

Desde `App`, iniciar solamente PostgreSQL cuando la tarea lo necesite:

```powershell
docker compose up -d db
docker compose ps db
```

La imagen local es PostgreSQL 16 y publica el puerto 5432. Si ya lo usa otro
servicio, resolver el puerto antes de levantar otro contenedor. No detener ni
eliminar servicios o volúmenes ajenos para liberar ese puerto.

Desde `App/backend`, en una terminal dedicada al entorno local:

```powershell
$env:DATABASE_URL = 'postgresql://monu:monu@127.0.0.1:5432/monuburger'
$env:ENTORNO = 'desarrollo'
.\.venv\Scripts\python.exe -m scripts.migrate --status
.\.venv\Scripts\python.exe -m scripts.migrate --seed
```

La URL del ejemplo corresponde a los valores locales por defecto de Compose;
ajustarla si se configuraron otros. Las variables de esa terminal prevalecen
sobre `.env`. `--seed` escribe datos y no es una verificación de solo lectura.
`--status` no aplica migraciones, pero crea la tabla de control si falta.
No ejecutar estos comandos contra la base compartida como preparación rutinaria
de una tarea de documentación. Para cambios de esquema, seguir
[GUIA_EQUIPO.md](GUIA_EQUIPO.md).

## Iniciar la aplicación

Desde `App/backend`, con la base configurada:

```powershell
.\.venv\Scripts\python.exe run.py
```

`run.py` fija `SelectorEventLoop` antes de Uvicorn en Windows. La API publica
`http://localhost:8000/docs` y `/api/salud`. Un healthcheck `degradado` significa
que la API arrancó pero la base no respondió.

En otra terminal, desde `App/frontend`:

```powershell
npm run dev
```

Vite sirve normalmente en `http://localhost:5173` y reenvía `/api` al backend.
`VITE_API_URL` permite otra base pública; al cambiar variables del build hay
que recompilar. Nunca poner contraseñas, tokens de proveedores o `JWT_SECRET`
en variables `VITE_*`.

## Elegir qué verificar

| Cambio | Verificación pertinente |
| --- | --- |
| Documentación, roles, skills | Enlaces, rutas y comandos contra sus manifiestos; TOML/YAML, recursos de skills y `git diff --check`. No iniciar servicios. |
| Regla de dominio o caso de uso | Tests específicos del módulo; Ruff sobre archivos afectados. |
| Routers o composición | Tests del contrato afectado y `tests/test_arquitectura.py`; permisos con y sin sesión. |
| SQL, migraciones, transacciones | PostgreSQL descartable, migraciones y tests del área; suite completa cuando cambian contratos comunes. |
| Frontend | `npm run lint` y `npm run build`; navegador para el recorrido, foco y responsive si hay cambio de interfaz. |

Desde `App/backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_arquitectura.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_stock_consumo_servicio.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Los dos primeros son ejemplos de selección, no pasos obligatorios para toda tarea.
Las pruebas SQL/HTTP escriben: unas revierten su transacción, y las HTTP y la de
concurrencia de stock confirman y limpian con el pool real. Por eso
`tests/soporte_bd.py` solo las ejecuta si `DATABASE_URL` apunta a `localhost`,
`127.0.0.1`, `::1`, un socket Unix o al servicio `db` de Compose (también revisa
`hostaddr`, `service` y `PGHOST`/`PGHOSTADDR`/`PGSERVICE`). Con `App/.env` hacia la base
compartida se **omiten** con ese motivo (`-rs` lo muestra). `MONU_PERMITIR_BD_REMOTA=1`
desactiva la guarda: solo para una base remota descartable y nunca en tareas de agentes.
Informar aprobadas y omitidas por separado.

Base descartable para la suite completa, sin tocar el volumen de Compose
(requiere Docker en ejecución; `--rm` la elimina al detenerla):

```powershell
docker run --rm -d --name monu_pg_pruebas -e POSTGRES_USER=monu -e POSTGRES_PASSWORD=monu `
  -e POSTGRES_DB=monuburger -p 55432:5432 postgres:16-alpine
$env:DATABASE_URL = 'postgresql://monu:monu@127.0.0.1:55432/monuburger'
.\.venv\Scripts\python.exe -m scripts.migrate --seed
.\.venv\Scripts\python.exe -m pytest -q -rs
docker stop monu_pg_pruebas
```

Desde `App/frontend`:

```powershell
npm run lint
npm run build
npm run test:portales
npm run test:panel
npm run test:operacion
npm run test:validaciones
```

El lint ejecuta oxlint; build genera `dist/` con Vite. No hay script `npm test`
ni suite de navegador en el manifiesto actual. Un build exitoso no prueba login,
pagos ni apariencia. La deuda heredada se registra en [DEUDA_TECNICA.md](DEUDA_TECNICA.md).
`test:portales` verifica rutas mediante renderizado React y el proxy con HTTP local,
sin base de datos. `test:panel` cubre métricas, reportes por fechas, clientes reales, cargas compartidas,
sondeo condicionado y respuestas tardías de catálogo/stock frente a escrituras.
Analítica agrega pruebas de validación y aplicación de filtros, vacío, errores con
reintento, separación de permisos financieros y respuestas atrasadas de otros períodos
o sesiones. `tests/vite-test-server.js` asigna una caché por proceso/servidor bajo
`node_modules/.vite-tests`; mantenerla separada de la caché del Vite de desarrollo.
`test:validaciones` agrega regresiones de sesión, permisos, cliente HTTP, campos,
respuestas incompletas, conservación de borradores y privacidad ante 401/403.
Para ejecutar todos los archivos de pruebas de frontend: `node --test tests/*.test.js`.
`npm run test:caja` ejecuta las regresiones de contrato, controlador y UI de Caja;
el CI también las ejecuta. `npm run test:caja-browser` usa Chromium y Playwright
preparados externamente (o `MONU_PLAYWRIGHT_PATH` apuntando al paquete instalado),
con fixtures sin backend y caché propia en `.vite-tests`.
Las pruebas de Caja usan fixtures de `/api/caja` y cubren contrato, permisos,
concurrencia visible, observaciones y recuperación de respuestas perdidas. No
simular éxito mediante un acuse parcial ni ejecutar generación/aprobación contra
la API o base compartida como comprobación. Los comandos y resultados efectivamente
ejecutados se registran en la entrega y en la
[matriz de Caja](VALIDACIONES_FRONTEND.md#caja-contrato-y-verificación).
La [matriz de auditoría](VALIDACIONES_FRONTEND.md) distingue esta cobertura del navegador.
`node tests/browser-validaciones.mjs` ejecuta la comprobación con Chromium y
Playwright ya preparados; opcionalmente admite `MONU_PLAYWRIGHT_PATH` para el módulo
y `MONU_CHROMIUM_PATH` para el ejecutable. Usa sólo fixtures, bloquea API externas,
deshabilita el proxy al backend y escribe evidencias en la carpeta temporal del sistema.
`test:operacion` cubre comandos HTTP, reintentos financieros,
versiones, frescura y renderizado de formularios operativos; no reemplaza una
prueba interactiva en navegador. Para las variantes `build:clientes` y `build:personal`, la
configuración de Pages y los checks posteriores, ver [despliegue](DESPLIEGUE.md).

Desde la raíz al terminar:

```powershell
git diff --check
git diff --stat
git status --short --branch
```

## Demostración del bot

El bot usa el backend con WhatsApp Cloud API y Gemini, sin n8n.
La [guía de WhatsApp](WHATSAPP_DESARROLLO.md) incluye una demostración reproducible
sin credenciales, el worker `python -m scripts.whatsapp_worker`, las variables
backend y la configuración posterior del webhook HTTPS con recursos de prueba.
La demostración exige una URL local explícita y escribe pedidos ficticios en esa
base descartable; no usar la base compartida. Los paneles del personal actualizan
solo pedidos cada ocho segundos, con pausa en pestañas ocultas; la bandeja de
comprobantes y cambios tiene actualización manual.

El [chat web de demostración](WHATSAPP_DESARROLLO.md#chat-web-de-demostración)
agrega `CHAT_DEMO_HABILITADO=true` para continuar el carrito dentro del mismo
menú, sin copiar mensajes al simulador. Usa WhatsApp simulado y permite Gemini
real o simulado por configuración; requiere la migración 027, cookie de sesión,
base local explícita y el mismo worker. Está desactivado por defecto; la
[publicación autorizada](WHATSAPP_DESARROLLO.md#publicación-autorizada-en-la-base-compartida)
permite usar la base compartida mediante un parámetro persistido sin ejecutar
pruebas ni seed en ella.

## Esquema generado

Después de un cambio SQL, desde `App/backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.diccionario
.\.venv\Scripts\python.exe -m scripts.der
```

Revisar el diff de `docs/DICCIONARIO_DATOS.md` y `docs/DER.md`. No editar a mano
esos resultados ni regenerarlos por una tarea que no cambió el esquema.

## CI y publicación

[ci.yml](../.github/workflows/ci.yml) corre en push a `main` y en pull requests:

- Frontend: Node 22, `npm ci`, oxlint, pruebas de portales/panel/caja/operación/validaciones y build.
- Backend: Python 3.12, PostgreSQL 16 descartable, dependencias, Ruff, migraciones
  con seed, estado, pytest y comprobación del esquema generado.

El CI no despliega. Ruff queda sin observaciones desde el 17/10/2026 y oxlint
solo emite advertencias (no fallan el paso); aun así, comprobar el resultado real
del workflow antes de decir que está verde. No cambiar workflows ni ocultar fallos por
el solo hecho de preparar documentación.

El repositorio incluye fallback SPA para hosting del frontend y un Dockerfile
backend. Sus archivos no prueban publicación activa ni autorizan un despliegue.
Antes de publicar, confirmar el destino y la configuración de la tarea concreta.
