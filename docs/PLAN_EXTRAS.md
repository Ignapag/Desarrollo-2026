# Extras de ingredientes — plan local, 29/10/2026

Objetivo: agregar porciones reales de ingredientes de la receta elegida, con precio,
stock y composición persistidos hasta cocina. Alcance inicial: trabajar en el checkout
actual preservando cambios previos, sin commits ni despliegue. Tras verificar la
implementación, el usuario autorizó expresamente su publicación el 29/10/2026.

Decisión: reutilizar `producto_opcion` y configurar desde recetas el precio de venta,
la cantidad por porción en la unidad del inventario y el máximo por hamburguesa.
No se cargan precios orientativos: opciones sin configuración completa no se venden.
Se descarta texto libre porque no permite validar ni descontar stock.

## Etapas y contratos

- [x] Backend y persistencia: `extras: [{ingrediente_id, cantidad}]` en cada ítem;
  validación estricta, pertenencia a receta/variante, límites y conflicto con retiros.
  Catálogo `extras_disponibles` con nombre, unidad, cantidad_requerida, precio,
  max_por_item y variantes. Configuración `extras` en GET/PUT receta; omisión preserva.
  Congelar extras y composición efectiva; usar transacciones y controles existentes.
- [x] Interfaz: configurar extras en editor de receta; cantidades de cero al máximo
  en menú, precio total visible, exclusión mutua con retiros y revisión por variante.
  Identidad estable de carrito por variante, retiros y extras. Mostrar desglose.
- [x] WhatsApp/chat y cocina: transportar datos estructurados al borrador, conservar
  en ediciones, convertir al pedido y mostrar nombres, cantidades y porciones.
- [x] Verificar: pruebas de contratos y UI, stock insuficiente/manipulación/reintentos,
  cancelación/edición; lint y build; navegador escritorio/móvil; revisión independiente.

## Evidencia y restricciones

Pruebas de base exclusivamente en PostgreSQL descartable local explícito.
Mantener 032_intentos_login.sql y modificaciones previas de autenticación/proxy.
Nueva migración con siguiente número disponible, sin editar las aplicadas.
No cambiar reglas de pagos ni variantes para representar extras.
Revisión: precios cambiados, ingredientes inactivos, variantes con recetas propias,
preservación de extras al editar y snapshots utilizados para devoluciones.

La configuración comercial queda a cargo del local antes de habilitar cada extra.

## Revisión independiente

Se corrigieron la omisión de extras al dar de alta un producto, la mezcla en carrito
de precios/porciones distintos, una variable de edición y el retiro contradictorio
desde revisión heredada de WhatsApp. También se restringió la nueva demanda de
extras a productos/categorías activos, conservando las reducciones históricas.

Navegador real local: 1440×1000 y 390×844. Configuración desde Receta, extras en
gramos y unidades, cero/máximo, retiro excluyente, variante, carrito con dos
configuraciones, chat simulado y comanda de cocina: aprobado sin errores JavaScript.
Evidencia final: carpeta temporal `monu-extras-browser-1793247510963`, con
`report.json` y capturas de configuración, menú, carrito, chat y cocina.
Se verificó también el agregado por teclado y controles de al menos 44×44 px.
No se comprobó envío real por Meta ni interpretación con Gemini: se utilizó el
chat habilitado con proveedores simulados y API/PostgreSQL reales locales.

## Verificación final ejecutada

- Frontend: 446 pruebas aprobadas, cero omitidas, con `node --test` sobre todos
  los archivos `tests/*.test.js`; `npm run lint` y `npm run build` aprobados.
  Lint mantiene dos advertencias de Fast Refresh en contextos existentes.
- Backend: 419 pruebas aprobadas, cero omitidas, en la suite conjunta de extras,
  recetas, stock, edición, recuperaciones, pedidos, WhatsApp, HTTP y arquitectura.
  Ruff aprobado. Pytest informa una deprecación de Starlette/AnyIO.
- Base `monu_extras_suite` creada vacía en PostgreSQL local puerto 55439 y migrada
  con seed hasta 033. Se separó de `monu_extras`, usada por navegador: algunas
  pruebas históricas esperan cero pedidos iniciales y fallan con fixtures de UI.
- Para la suite conjunta se usó `pytest -p tests.test_stock_consumo_bd` para
  registrar explícitamente su fixture compartida de concurrencia; no se alteraron
  pruebas ni reglas para resolver el orden de descubrimiento.
- Migración desde vacío, enlaces locales y `git diff --check` aprobados.

El local debe configurar precios, porciones y máximos para habilitar cada extra.
La etapa local terminó sin SQL en la base compartida, commits, push ni despliegues.
La publicación posterior autorizada incluye la migración 033 mediante el arranque
existente de Render, sin seed ni pruebas sobre la base publicada.

Preparación para publicar: suite backend completa con `pytest -q -rs`, 1.369
pruebas aprobadas sin omisiones en otra base PostgreSQL local vacía, sin registrar
fixtures adicionales. Ruff global y builds `build:clientes`/`build:personal`
aprobados; `test:extras`, 34 pruebas aprobadas.
