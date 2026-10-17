# Código limpio

Convenciones para cambios nuevos y para el código afectado por una tarea.
No justifican reformatear ni reescribir módulos que el pedido no necesita.
Los límites entre capacidades se describen en [arquitectura](ARQUITECTURA.md).

## Responsabilidades e interfaces

- Mantener juntas las reglas que cambian por el mismo motivo. Una función o
  módulo debe exponer una responsabilidad reconocible y ocultar sus detalles.
- Extender el módulo existente antes de crear helpers globales, factories o capas.
  Extraer una abstracción cuando reduzca complejidad real de sus consumidores.
- Usar nombres del negocio: pedido, ingrediente, pago, cierre, repartidor.
  Evitar `manager`, `utils` o `data` para responsabilidades nuevas ambiguas.
- Validar en la frontera correspondiente: formato HTTP en esquemas; invariantes
  en dominio/aplicación; integridad relacional en SQL. El servidor valida precios,
  permisos, stock y estados aunque el navegador ya los haya comprobado.
- Usar retornos tempranos para casos inválidos y tipos explícitos en contratos.
  Los comentarios explican decisiones o restricciones, no repiten cada línea.
- Evitar una función por cada línea y una clase por cada llamada. Preferir una
  interfaz pequeña que permita probar comportamiento observable.

## Python

- Python 3.12 o superior; `snake_case` en funciones, módulos y variables;
  `PascalCase` en clases. Mantener la terminología española del backend.
- Ruff toma su configuración de `App/backend/pyproject.toml`: objetivo `py312`,
  ancho 100 y reglas `E,F,I,UP,B,SIM`, con `B008` excluida por `Depends()`.
- Dominio sin FastAPI, Pydantic, psycopg ni `app.core`; aplicación sin FastAPI,
  Pydantic ni psycopg. Los casos de uso reciben contratos pequeños (`Protocol`
  cuando aporta) y los adaptadores los cumplen.
- Las excepciones compartidas se importan siempre de `app/errores.py`; su
  traducción HTTP está en `app/core/errores.py`. Evitar excepciones paralelas.
  Un error del driver (`psycopg.errors.*`) se traduce en el adaptador SQL.
- No bloquear el event loop con I/O síncrono nuevo en un flujo async.
  Capturar excepciones concretas; no ocultar fallos con `except: pass`.
- Mantener `Decimal` para importes y cantidades que requieren precisión;
  no introducir `float` en cálculos monetarios. Respetar UTC en instantes.

## React y JavaScript

- La entrada es `index.html` → `src/main.jsx` → `src/App.jsx`; el código es JSX.
  No introducir TypeScript ni una segunda entrada por una tarea localizada.
- Componentes en `PascalCase`, hooks con prefijo `use`, variables con el estilo
  existente de la carpeta. Código sin consumidores no se deja "para después".
- Separar presentación, estado e interacción HTTP cuando tengan responsabilidades
  distintas. Reutilizar `shared/api/http.js` y sus cookies de sesión.
- Modelar carga, vacío, éxito y error. Informar el fallo real: no mostrar éxito
  si la API rechazó la operación ni reemplazar el error por datos simulados.
- Una actualización optimista debe restaurar el estado ante error y reconciliarse
  con la respuesta del servidor. No duplicar un pago o descuento de stock al reintentar.
- Efectos solo para sincronización externa. Limpiar timers y suscripciones;
  evitar efectos que solo recalculan valores derivados y dependencias omitidas.
- Reutilizar tokens de `index.css` y componentes existentes. Mantener etiquetas,
  foco, teclado y diseño responsive en cambios de interfaz.
- `npm run lint` usa **oxlint** con `.oxlintrc.json`. No agregar una segunda
  herramienta de lint ni desactivar reglas para ocultar un defecto.

## SQL, transacciones y servicios externos

- SQL directo y parametrizado con `%s`; no interpolar entradas en consultas.
  Los identificadores dinámicos requieren una lista permitida y composición segura.
- Todo cambio de esquema va en una migración nueva numerada. No editar checksums
  de las migraciones aplicadas ni introducir IDs manuales que colisionen con seeds.
- Mantener la misma `UnidadDeTrabajo` entre escrituras de una operación atómica.
  El contexto de conexión confirma al salir o revierte ante excepción.
- Antes de modificar pagos, caja, consumo o reposición: revisar concurrencia,
  reintentos, bloqueos y transición de estados. No sumar commits en repositorios
  internos que rompan la transacción del caso de uso.
- No llamar proveedores externos desde el dominio. Aislarlos en adaptadores;
  conservar sus contratos y distinguir envío real de simulado.
- No exponer secretos, cookies ni datos personales en logs, respuestas o `VITE_*`.

## Pruebas y revisión

Las pruebas demuestran reglas y regresiones, no la forma de la implementación.
En un bug, reproducir el caso o establecer su causa antes del cambio; cubrirlo
cuando corresponda. En un cambio de prosa no agregar pruebas de producto.
Las pruebas con base usan el fixture `uow` (transacción revertida) de
`tests/conftest.py`. Si necesitan otra conexión (concurrencia, pool HTTP),
primero pasan por `conectar_o_omitir()` o `exigir_base_descartable()` de
`tests/soporte_bd.py`.
Una regla estructural nueva se fija en `tests/test_arquitectura.py`.

La revisión mira primero comportamiento y permisos, después contratos,
transacciones y errores, y finalmente claridad. Comandos y límites de evidencia
en [desarrollo](DESARROLLO.md). No presentar tests omitidos como aprobados.
