# Edición de productos existentes — 29/10/2026

El usuario solicita editar nombre, precio, imágenes y los datos disponibles de
receta de cada producto ya creado, y publicar el resultado en main.

Se amplía el catálogo con «Editar producto» y un formulario completo: nombre,
descripción, categoría, precio base y precios/recetas de variantes, imagen,
orden, activo, ingredientes y extras. Se conserva el acceso existente a Receta.
Los productos inactivos también se pueden editar sin reactivarlos.

## Contrato y decisiones

- GET `/api/productos/{id}`: detalle completo para el editor y categorías activas
  (incluye la actual si está inactiva); permiso `productos.ver_receta`.
- PUT `/api/productos/{id}`: datos completos de alta más
  `actualizado_en_esperado`; permiso `productos.gestionar`. Guarda metadatos,
  receta, variantes y extras dentro de la misma transacción y conserva el ID.
- Control de concurrencia compartido con receta/estado. Una falla conserva el
  borrador y no anuncia éxito; volver a cargar descarta cambios explícitamente.
- Precios de venta positivos y exactos; imagen reemplazable por archivo raster
  de hasta 5 MiB o URL/ruta del sitio, con opción de quitarla. No se descargan
  imágenes externas desde el backend. Dips Extra conserva su regla sin extras.
- Pedidos existentes conservan nombres, precios y composición históricos.
  Cambiar un producto no consume ni repone inventario. No se sobrescribe la
  configuración interna de carga de reparto.
- Se trabaja aislado de los cambios concurrentes de stock del checkout original.

## Etapas

- [x] Backend: contratos, validación, actualización atómica y pruebas de SQL/HTTP.
- [x] Frontend: formulario, fotos, edición de receta y variantes, catálogo e inactivos.
- [x] Verificar permisos, concurrencia, errores, persistencia e historial; navegador
  escritorio/móvil, lint, build y suites con PostgreSQL descartable.
- [ ] Revisión independiente, PR, CI y publicación en main; verificar sitios/API.

La publicación está autorizada; las pruebas y fixtures nunca usan la base compartida.

## Revisión y evidencia

Revisión independiente realizada. Se corrigieron la carrera alta/edición de nombres,
el acceso a productos activos ocultos por categorías inactivas y la preservación del
estado histórico al editar esos productos; no se permite reactivarlos en una
categoría inactiva. Los nuevos tests frontend se incorporaron a `test:panel` del CI.

Navegador real local, escritorio 1440×1000 y móvil 390×844: edición de metadatos,
precios y nombres de variantes, cantidad de receta, máximo de extras, foto subida y
eliminada, stock intacto, conflicto de versión con borrador preservado y edición de
inactivos sin reactivación. Sin errores JavaScript. Capturas y reporte en la carpeta
temporal `monu-edicion-browser-1793249893833`.

Los tests automáticos usan `monu_edicion`; navegador usa `monu_edicion_browser`:
bases diferentes del PostgreSQL descartable local puerto 55441. No hay migración
nueva: se reutilizan las tablas y la versión temporal existentes del producto.

Verificación previa a publicación: 1.400 pruebas backend completas y 457 frontend
aprobadas, sin omisiones. Los 9 casos nuevos frontend están en `test:panel` del CI.
Ruff global, lint, builds de clientes/personal, enlaces y `git diff --check`
aprobados. Persisten dos advertencias de Fast Refresh y una deprecación de
Starlette/AnyIO ya presentes en el entorno.
