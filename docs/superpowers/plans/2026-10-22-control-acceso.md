# Control de acceso: diseño y plan

Objetivo autorizado: reemplazar la pantalla ficticia por asignación de roles a usuarios
y edición persistente de permisos por módulo y acción para cada rol interno.

## Contratos

- Administrador conserva todas las capacidades y administra la matriz; Cliente no recibe
  permisos del panel. Dueño, Empleado y Repartidor tienen matrices editables.
- La migración 028 incorpora versiones de matriz y permisos por rol. Parte de los accesos
  actuales; Administrador también puede consultar reportes financieros.
- JWT identifica al usuario; cada request autenticado valida cuenta activa, rol y permisos
  actuales en PostgreSQL. Los tokens viejos no conservan privilegios retirados.
- Se preservan validaciones de propiedad, stock, pagos, versiones y transiciones.
- GET `/api/acceso`: catálogo de módulos/acciones y matrices de roles (solo administrador).
- PUT `/api/acceso/roles/{rol}`: `{permisos: string[], version: int}`, guarda atómicamente,
  registra auditoría y rechaza versiones obsoletas con 409. No admite permisos desconocidos
  ni cambios a las matrices protegidas de Administrador y Cliente.
- Login y `/api/auth/me` incluyen `permisos`. El panel consulta sesión periódicamente y al
  recuperar foco; oculta rutas ajenas y mantiene al backend como autoridad.
- Cambios de rol y desactivaciones no pueden dejar al sistema sin administrador activo.
- El menú público, webhook de Meta y chat demo mantienen su autenticación propia.

## Etapas y verificación

- [x] Dominio de permisos, repositorio SQL, servicio de acceso y migración. Probar catálogo,
  matrices iniciales, guardado, versión obsoleta, permisos inválidos y auditoría con
  PostgreSQL local descartable `127.0.0.1:55433`, nunca la base compartida.
- [x] Autorización vigente, endpoints de acceso y gestión de roles. Probar con la misma
  cookie antes/después de revocación, cambio de rol y desactivación; conservar rechazo
  anónimo antes de conexión y evitar que un permiso funcional elimine propiedad.
- [x] Integrar guardas funcionales y reglas de servicios en cada capacidad. Probar
  concesiones/revocaciones representativas y regresiones de pedidos/pagos/delivery.
- [x] Sustituir pantalla por datos reales, matriz accesible y control de navegación.
  Probar fallos HTTP, guardados concurrentes y actualización de sesión. Comprobación
  visual responsive pendiente: la revisión automática rechazó el intento con Chrome.
- [x] Ejecutar suites afectadas, arquitectura, lint/build y revisión del diff. Regenerar
  diccionario/DER desde SQL; documentar contrato, límites y resultados reales.

No incluye crear roles nuevos, sobreescrituras por usuario, publicar cambios, ni modificar
permisos de personas reales como prueba. La comprobación funcional usa cuentas ficticias.

Resultados locales: backend 1.106 aprobadas, cero omitidas (una advertencia heredada
de AnyIO); frontend 159 aprobadas, lint sin errores (dos advertencias de exportación de
contextos), build aprobado. Ruff completo y diff correctos. Migraciones 001–028 aplicadas
en PostgreSQL 16 descartable, sin pendientes. Login admin y lectura HTTP real de usuarios
y matrices verificados contra esa instancia. No se aplicó la migración en la base compartida.
