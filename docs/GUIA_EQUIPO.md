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
python -m uvicorn app.main:app --reload
# y abrir http://localhost:8000/api/salud  →  "estado": "ok"
```

Si `/api/salud` dice `degradado`, no estás llegando a la base: revisá la URL,
el `sslmode` y si tu IP necesita estar habilitada en el panel del proveedor.

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

## 4. Referencia del esquema

**[DICCIONARIO_DATOS.md](DICCIONARIO_DATOS.md)** tiene las 27 tablas con sus
columnas, tipos, obligatoriedad, claves foráneas y valores permitidos en cada
campo de estado. Es la fuente de verdad para programar.

Se genera del SQL, no se escribe a mano:

```bash
cd App/backend
python -m scripts.diccionario
```

Correlo después de cada migración nueva.

## 5. Convenciones de código

- Tablas, columnas y código en **español**, `snake_case`.
- **SQL directo con psycopg, sin ORM** (así lo define el stack del proyecto).
- Toda consulta **parametrizada** con `%s`. Nunca interpolar valores en el
  string SQL: es la puerta de entrada a una inyección SQL.
- Montos en `NUMERIC(12,2)` y cantidades en `NUMERIC(12,3)`: en Python llegan
  como `Decimal`. No los conviertas a `float` para hacer cuentas de dinero.
- Fechas en `TIMESTAMPTZ`.
- Errores de negocio: usar las excepciones de `app/core/errores.py`, no
  `HTTPException`.

## 6. Estructura de un módulo

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

## 7. Qué hay implementado

| Módulo | Estado | Responsable |
|--------|--------|-------------|
| Base de datos (esquema completo) | ✅ 27 tablas, 3 vistas, 5 funciones, 3 triggers | Ignacio Pagotto |
| Asignación de repartidores | 🔨 en curso | Ignacio Pagotto |
| Pedidos · Menú · Stock · Pagos y Caja · Reportes · Bot · Usuarios | ⬜ | resto del grupo |

El esquema ya contempla **todos** los módulos: las tablas de pedidos, pagos,
stock y notificaciones están creadas y esperando a que cada uno construya
encima. No hace falta pedir tablas nuevas para lo que ya está en el
diccionario.

## 8. Decisiones de modelado que conviene conocer

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
