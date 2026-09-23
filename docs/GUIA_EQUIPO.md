# Guía de trabajo con la base de datos

Grupo 19 · Seminario Integrador 2026 · Sistema de Gestión Monu Burger

Esta guía es para los seis integrantes. La base de datos es **una sola,
compartida en la nube**, y da soporte a todos los módulos del sistema.

**Responsable de la base:** Ignacio Pagotto. Cualquier cambio de esquema pasa
por él.

---

## 1. Conectarse

Las credenciales **no se versionan**: `.env` está en el `.gitignore` de la raíz y tiene que
seguir estándolo. Pedile la cadena de conexión al responsable de la base y
armá tu `.env` local:

```bash
cd App
cp .env.example .env
```

```ini
DATABASE_URL=postgresql://usuario:clave@host:5432/monuburger?sslmode=require
```

> Los proveedores en la nube (Supabase, Neon) exigen `sslmode=require`. Si lo
> omitís, la conexión falla con un error poco claro.

Probá que conecta:

```bash
cd App/backend
python -m scripts.migrate --status     # debería decir "Sin migraciones pendientes"
python run.py                          # NO `uvicorn app.main:app`, ver nota abajo
# y abrir http://localhost:8000/api/salud  →  "estado": "ok"
```

Si `/api/salud` dice `degradado`, no estás llegando a la base: revisá la URL,
el `sslmode` y si tu IP necesita estar habilitada en el panel del proveedor.

> **Windows:** levantá la API con `python run.py`, no con `uvicorn app.main:app`.
> psycopg en modo async necesita `SelectorEventLoop` y Python usa
> `ProactorEventLoop` por defecto; `run.py` fija la política antes de que
> uvicorn cree el loop. Con uvicorn directo la API arranca pero ninguna
> consulta funciona y todo responde 503.

## 2. Qué NO hacer nunca

La base es compartida: lo que rompas, lo rompés para los seis.

| No hacer | Por qué |
|----------|---------|
| `migrate --reset` | Borra el esquema **completo**, con los datos de todos. El script lo bloquea si la base no es local, pero no te confíes. |
| `DROP` o `TRUNCATE` a mano desde DBeaver | Igual que lo anterior, sin red de contención. |
| Editar una migración ya aplicada | El runner guarda un checksum y te avisa, pero para ese momento tu base y la del resto ya divergieron. |
| Commitear el `.env` | Son credenciales de una base compartida. |
| Cargar datos de prueba masivos | Ensucian el trabajo de los demás. Para eso, levantá una base local. |

Si necesitás experimentar con libertad, levantá tu propia base con Docker
(`docker compose up -d db`) y apuntá tu `.env` a `localhost`. Ahí sí podés
resetear cuanto quieras.

## 3. Cómo pedir un cambio de esquema

Si tu módulo necesita una tabla, una columna o un índice que no existe:

1. **Avisá antes de escribir código** que dependa de eso.
2. Decí qué necesitás y para qué requisito funcional es.
3. El responsable agrega una **migración nueva numerada**
   (`007_...sql`, `008_...sql`), nunca modifica una anterior.
4. Se regenera el diccionario y se avisa al grupo.
5. Cada uno corre `python -m scripts.migrate` para quedar al día.

**Por qué esta regla:** una migración aplicada ya corrió en la base compartida.
Editarla no la vuelve a ejecutar, así que tu archivo y la base real dicen cosas
distintas, y el próximo que clone el repo va a construir un esquema diferente
del que está en producción. Es el tipo de problema que aparece recién en la
integración final, cuando ya no hay tiempo.

## 4. Flujo de trabajo con Git

Cada uno clona el repositorio en su máquina y trabaja **en su propia rama**.
Lo que cada uno hace se integra a `main` por Pull Request.

```bash
git clone https://github.com/Ignapag/Proyecto---Seminario-Integrador-2026.git
cd Proyecto---Seminario-Integrador-2026
git checkout -b TuNombre       # la primera vez
```

### El ciclo de cada día

```bash
git checkout main
git pull                       # traer lo último del grupo
git checkout TuNombre          # volver a tu rama
git merge main                 # incorporar lo nuevo a tu trabajo

# ... trabajás ...

git add .
git commit -m "qué hiciste"
git push
```

Cuando terminás algo que vale la pena integrar, abrís el **Pull Request** en
GitHub. Alguien del grupo lo revisa, se mergea a `main`, y todos vuelven a
hacer `git pull`.

En VS Code todo esto está en el panel de Source Control (`Ctrl+Shift+G`): el
selector de rama abajo a la izquierda y los botones de sincronizar. No hace
falta usar la terminal.

### Qué revisa GitHub solo en cada PR

Hay integración continua configurada (`.github/workflows/ci.yml`). En cada
push a `main` y en **cada Pull Request**, GitHub levanta una máquina y corre:

1. `ruff` sobre el backend
2. Las 8 migraciones **sobre un PostgreSQL vacío**, más el seed
3. Las 68 pruebas
4. Un chequeo de que el diccionario de datos y el DER estén al día con el SQL

Si algo falla, el PR muestra una cruz roja y no conviene mergearlo.

El PostgreSQL de CI es descartable y vive dos minutos: **no toca la base
compartida**, así que las pruebas no pueden ensuciarla. Y como las migraciones
se aplican desde cero, se detectan los errores que en una base ya migrada no
se ven — justo antes de que alguien los aplique sobre la base del grupo.

Si tocás el esquema, antes de pushear regenerá la documentación:

```bash
cd App/backend
python -m scripts.diccionario && python -m scripts.der
```

### Las tres reglas que evitan el dolor

1. **Nadie trabaja directo en `main`.** `main` es lo que funciona; tu rama es
   donde experimentás.
2. **Traé `main` a tu rama todos los días**, no una vez por mes. Es la regla
   que más se incumple y la que más cuesta: cuanto más tiempo trabajás aislado,
   más diverge tu código del de los demás y más doloroso es el merge.
3. **Commits chicos y frecuentes**, uno por cosa terminada. No uno gigante al
   final de la semana.

### Por qué la regla 2 importa

Un caso real de este proyecto: durante un tiempo convivieron dos frontends
distintos, uno en `App/frontend/` (JSX) y otro en `frontend/` (TypeScript +
Tailwind), en ramas separadas. No eran el mismo proyecto con cambios: eran dos
proyectos Vite independientes.

Git no avisa de eso — no hay conflicto que resolver, simplemente termina
habiendo trabajo duplicado que alguien tiene que descartar. Integrando seguido
se detecta el primer día, no en la entrega.

### La base de datos NO funciona así

Esta es la diferencia importante. Git te protege de pisar el trabajo de otro:
podés equivocarte en tu rama sin afectar a nadie, y siempre se puede volver
atrás.

**La base compartida no.** Si alguien borra una tabla, la borró para los seis
en ese instante. No hay rama, no hay revisión previa, no hay `git revert`. Por
eso valen las reglas de la sección 2, y por eso el script bloquea `--reset`
contra la base remota. Si necesitás romper cosas para probar, levantá un
Postgres local con Docker.

## 5. Referencia del esquema

**[DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md)** tiene las 27 tablas con sus
columnas, tipos, obligatoriedad, claves foráneas y valores permitidos en cada
campo de estado. Es la fuente de verdad para programar.

**[DER.md](DER.md)** es el diagrama entidad-relación, con un diagrama general
y uno por módulo. GitHub los renderiza solos.

Los dos se generan del SQL, no se escriben a mano:

```bash
cd App/backend
python -m scripts.diccionario
python -m scripts.der
```

Correlos después de cada migración nueva.

## 6. Convenciones de código

- Tablas, columnas y código en **español**, `snake_case`.
- **SQL directo con psycopg, sin ORM** (así lo define el stack del proyecto).
- Toda consulta **parametrizada** con `%s`. Nunca interpolar valores en el
  string SQL: es la puerta de entrada a una inyección SQL.
- Montos en `NUMERIC(12,2)` y cantidades en `NUMERIC(12,3)`: en Python llegan
  como `Decimal`. No los conviertas a `float` para hacer cuentas de dinero.
- Fechas en `TIMESTAMPTZ`.
- Errores de negocio: usar las excepciones de `app/core/errores.py`, no
  `HTTPException`.

## 7. Estructura de un módulo

Cada módulo respeta las cuatro capas de Clean Architecture:

```
app/modules/<modulo>/
├── domain/           entidades y reglas puras (sin FastAPI ni psycopg)
├── application/      casos de uso: orquestan reglas y transacciones
├── infrastructure/   repositorios con SQL directo
└── presentation/     router FastAPI + esquemas Pydantic
```

Y se monta en `app/main.py` con `app.include_router(...)`.

Al escribir endpoints con autenticación, declarar la **dependencia de rol antes
que `UoW`** en la firma: FastAPI resuelve en orden, y así un request sin sesión
se rechaza sin gastar una conexión a la base.

## 8. Qué hay implementado

| Módulo | Estado | Responsable |
|--------|--------|-------------|
| Base de datos (esquema completo) | ✅ **aplicado y funcionando** en Supabase | Ignacio Pagotto |
| Asignación de repartidores | ✅ implementada y probada | Ignacio Pagotto |
| Usuarios y seguridad (login, roles, auditoría) | ✅ implementado y probado | Tomás Arber Aramburu |
| Notificaciones / Bot de WhatsApp | 🔨 plantillas y encolado listos, falta la integración con n8n | Tomás Arber Aramburu (n8n: resto del grupo) |
| Pedidos · Menú · Stock · Pagos y Caja · Reportes | ⬜ | resto del grupo |

La base ya está creada, con el esquema aplicado y datos de desarrollo cargados:
podés empezar a consultarla hoy. El esquema contempla **todos** los módulos: las tablas de pedidos, pagos,
stock y notificaciones están creadas y esperando a que cada uno construya
encima. No hace falta pedir tablas nuevas para lo que ya está en el
diccionario.

## 9. Decisiones de modelado que conviene conocer

Están detalladas en [CAMBIOS_DER.md](CAMBIOS_DER.md), pero estas afectan a todos:

- **El stock vive solo en `ingrediente`**, no en `producto`. La disponibilidad
  de un producto se deriva de la vista `producto_disponible`.
- **Los precios se congelan** en `pedido_item` al confirmar el pedido. Un cambio
  de precio en el menú no altera pedidos ni reportes históricos.
- **Cada cambio de estado de un pedido** va a `pedido_estado_historial`, con
  usuario y timestamp. No alcanza con actualizar `pedido.estado`.
- **Las acciones críticas se auditan** en la tabla `auditoria` (RNF-09): alta y
  cambio de estado de pedidos, modificaciones del menú, registros de caja y
  cambios de configuración.
- **Un pago conciliado y un cierre de caja aprobado son inmutables**: hay
  triggers que lo impiden a nivel base, no solo en la aplicación.
