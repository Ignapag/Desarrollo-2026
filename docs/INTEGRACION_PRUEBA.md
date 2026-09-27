# Integración unificada — `integracion/prueba`

Fecha de verificación: 27 de septiembre de 2026  
Base: `origin/main` (`9b5f895`)

## Ramas integradas y orden

Cada rama se incorporó con `git merge --no-ff` y sin modificar `main` ni las ramas originales:

1. `Tomas` — usuarios, autenticación y autorización.
2. `Jose` — stock y reportes.
3. `feature/registro-pagos-efectivo`.
4. `feature/validacion-pagos`.
5. `feature/integracion-billeteras-virtuales`.
6. `feature/caja-consolidacion-ingresos`.
7. `feature/caja-generacion-resumen`.
8. `feature/caja-aprobacion-bloqueo`.
9. `feature/conciliacion-pagos`.
10. `Juan` — frontend y flujo de pedidos.
11. `Emilio` — frontend elegido como base visual ante superposiciones, según lo acordado.

No se generaron merges vacíos para `Ignacio`, `Nicolas`, `backend`, `develop` y `frontend`: al momento de integrar no tenían commits exclusivos respecto de `main` o apuntaban al mismo historial.

Antes de los merges se detectó que `Emilio` estaba 10 commits detrás de `main` y `Juan` 9 commits detrás; se informó esta desactualización. `Tomas`, `Jose` y las ramas `feature/*` estaban solamente un commit detrás.

## Conflictos resueltos

- `app/core/dependencias.py` y `app/main.py`: se conservó una sola composición de aplicación, el descubrimiento automático de routers y las dependencias de sesión/roles. Las dependencias de negocio se movieron a la capa `presentation` de cada módulo.
- Configuración: se unificaron JWT, cookies HttpOnly, CORS y Mercado Pago; `.env.example` documenta las variables necesarias sin incluir secretos.
- Pagos/caja: se restauraron tanto la factoría del servicio de caja como `ServicioConciliacionDep`, que ramas distintas habían agregado/eliminado.
- Frontend `Juan`/`Emilio`: para los archivos visuales compartidos (`App.jsx`, estilos, bootstrap de React, `package.json` y configuración de PostCSS) prevaleció Emilio. Se conservaron componentes y tipos exclusivos de Juan y luego se conectaron ambos conjuntos a la API integrada.
- Los archivos compartidos se resolvieron sumando routers, dependencias y configuración; no se aplicó `ours`/`theirs` sobre módulos completos.

## Base de datos y SQL

- Se mantuvieron intactas las migraciones ya versionadas y sus checksums:
  `001_usuarios_y_seguridad.sql` a `008_funciones_geo_float.sql`, seguidas por `seed.sql`.
- Las ocho migraciones y el seed se ejecutaron en orden sobre PostgreSQL 16 vacío, en un contenedor aislado, y `scripts.migrate --status` informa **sin migraciones pendientes**.
- No fue necesaria una migración adicional: el esquema central ya contenía las tablas, relaciones, checks y enums utilizados por las ramas.
- Se alinearon las consultas de usuarios, stock, delivery, pagos y reportes con ese esquema. El escaneo final no encontró SQL construido con f-strings o concatenación; los valores variables usan parámetros `%s`.
- La creación de productos exige al menos un ingrediente y guarda su receta en la misma transacción, evitando productos imposibles de descontar del stock.
- Los seeds no introducen IDs manuales duplicados.

## Correcciones posteriores a los merges

- Se completaron los módulos autocontenidos `productos/` y `pedidos/` con dominio, aplicación, infraestructura SQL y presentación FastAPI.
- Se expusieron routers protegidos para stock y reportes y se protegieron delivery, pagos y caja por sesión/rol; el webhook de Mercado Pago permanece público por diseño.
- Se dejó un único pool Psycopg, una implementación JWT/cookie y dependencias de roles compartidas desde el módulo usuarios.
- Se corrigieron consultas SQL con tipos nulos ambiguos y variantes opcionales sin concatenar SQL.
- El frontend usa un cliente HTTP único con `credentials: 'include'`, autenticación real, rutas por rol y acciones reales para catálogo, stock, pedidos, cocina y pagos.
- Registro y recuperación de contraseña no tienen endpoints backend: se retiraron de las rutas públicas para no simular resultados exitosos.
- Los contratos TypeScript de pedido, estados y métodos de pago se alinearon con Pydantic.

## Verificación realizada

- Backend: `python -m compileall -q app` correcto.
- Tests: **236 passed**.
- Base desde cero: migraciones `001`–`008` + seed correctos, sin pendientes.
- API: iniciada con Uvicorn mediante `python run.py`; OpenAPI registró 49 rutas/56 operaciones y `/docs` respondió HTTP 200.
- Flujo real sobre PostgreSQL: login administrador y cliente → alta de producto con receta → creación de pedido → estado `EN_PREPARACION` → pago en efectivo `CONCILIADO`.
- Frontend: `npx tsc --noEmit` correcto.
- Frontend: `npm run build` correcto.
- Frontend: `npm run lint` termina sin errores; quedan advertencias no bloqueantes detalladas abajo.
- No se pudo realizar la inspección visual automatizada porque el navegador embebido no estuvo disponible en esta sesión. El servidor Vite sí inició correctamente y el contrato frontend/backend fue validado por tipado, build y flujo HTTP.

## Decisiones pendientes para el grupo

- El esquema implementado usa estados de pago `PENDIENTE`, `CONCILIADO` y `ANULADO`. Esto equivale funcionalmente a pendiente, aceptado y rechazado/anulado, pero conviene decidir si se renombran en una migración futura para coincidir literalmente con el DER original.
- Confirmar si se habilitará auto-registro y recuperación de contraseña. Hoy las cuentas se administran desde usuarios y no existen esos endpoints públicos.
- Definir credenciales y pruebas sandbox para Mercado Pago, WhatsApp Cloud API y n8n; no se probaron servicios externos reales.
- Acordar si el frontend conservará los datos mock como fallback de desarrollo o si se eliminan una vez estabilizada la API.

## Deuda técnica detectada

- Vite advierte que el bundle principal supera 500 kB; conviene dividir por rutas con imports dinámicos.
- El lint reporta advertencias heredadas de imports sin uso, archivos que mezclan contexto y componentes, y un efecto de sincronización en `DataContext`; no hay errores de lint.
- `ruff check app tests` aún reporta 50 observaciones estáticas heredadas de las ramas de pagos/caja y tests (principalmente longitud de línea, orden de imports y uso de `datetime.UTC`); no afectan la suite, pero el lint de Python no está verde.
- Las vistas de analítica, clientes y control de acceso todavía incluyen contenido demostrativo aunque los módulos backend principales ya están conectados.
- Falta una prueba end-to-end de navegador reproducible en CI.

## Checklist de validación manual

- [ ] Copiar `App/.env.example` a `App/.env` y completar solamente credenciales locales/sandbox.
- [ ] Crear una base vacía y ejecutar `python -m scripts.migrate --seed`; confirmar que no quedan migraciones pendientes.
- [ ] Iniciar backend con `python run.py` desde `App/backend` y verificar `/api/salud` y `/docs`.
- [ ] Iniciar frontend con `npm run dev` desde `App/frontend`.
- [ ] Iniciar sesión con cada rol: administrador, dueño, empleado, repartidor y cliente.
- [ ] Verificar que una persona sin sesión no acceda a rutas internas y que cada rol vea solamente su navegación autorizada.
- [ ] Crear categoría/ingrediente si corresponde, reponer stock y dar de alta un producto con receta.
- [ ] Como cliente, agregar el producto al carrito y crear un pedido para retiro.
- [ ] Crear también un pedido delivery con dirección nueva dentro de una zona activa.
- [ ] Avanzar el pedido por cocina: pendiente → en preparación → listo.
- [ ] Registrar un pago en efectivo y comprobar monto, vuelto, saldo y estado conciliado.
- [ ] Probar una preferencia de Mercado Pago solamente con credenciales sandbox.
- [ ] Asignar un repartidor disponible, iniciar viaje y completar entrega.
- [ ] Revisar movimientos de stock, auditoría, reportes y cierre de caja.
- [ ] Confirmar logout, expiración de cookie y rechazo de requests sin cookie.
- [ ] Ejecutar `pytest -q`, `npx tsc --noEmit`, `npm run build` y `npm run lint` en el entorno del equipo.
- [ ] Validar visualmente desktop y móvil antes de aprobar el PR.
