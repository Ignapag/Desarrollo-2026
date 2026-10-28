# Monu Burger — frontend

Interfaz React 19 con Vite 8, React Router y Tailwind CSS 4. Este es el único
frontend del repositorio. Las dependencias se fijan en `package-lock.json`.

Agentes: leer [AGENTS.md](AGENTS.md). La guía completa de preparación está en
[DESARROLLO.md](../../docs/DESARROLLO.md).

## Inicio

Desde esta carpeta, con Node 22 y npm:

```powershell
npm ci
npm run dev
```

Vite sirve normalmente en `http://localhost:5173` y reenvía `/api` a
`http://127.0.0.1:8000`. El backend se inicia por separado con `python run.py`
desde `App/backend`, usando su entorno Python y una base configurada.
`VITE_API_URL` permite una API pública distinta; nunca contiene secretos.

## Estructura y estado real

- Entrada: `index.html` → `src/main.jsx` → `src/App.jsx`.
- `src/auth/AuthContext.jsx` gestiona sesión real con la API y cookie HttpOnly.
- `src/shared/api/http.js` es el cliente HTTP común.
- `src/shared/store/DataContext.jsx` concentra datos y acciones de varias capacidades.
- `ordering/` (menú y carrito), `fulfillment/`, `kitchen/`, `inventory/` y
  `management/` contienen los recorridos de cliente y operación.
- Todo `src/` es JSX alcanzable desde `main.jsx`; no hay entradas alternativas.

El menú, catálogo, inventario y acciones operativas usan la API integrada.
En desarrollo completo y en la variante de clientes, `/` abre el menú público.
El carrito prepara un borrador sin cuenta ni teléfono;
el cliente lo envía por WhatsApp y el bot vincula al remitente antes de registrar
el pedido. Solo se ofrece ese canal en el checkout público, con efectivo o
transferencia pendiente de revisión humana. El personal conserva su login.
Contrato y vinculación en [WhatsApp](../../docs/WHATSAPP_DESARROLLO.md).
La variante de personal abre el login y solo registra gestión y reparto.
Los dos proyectos de Cloudflare Pages comparten este frontend; comandos y
configuración del proxy en [despliegue](../../docs/DESPLIEGUE.md).
`/register` y `/recover-password` redirigen a login: no hay vistas ni endpoints.
Algunas vistas de analítica, clientes y acceso todavía muestran contenido
demostrativo; no considerar la interfaz completamente validada para producción.
Ver [deuda técnica](../../docs/DEUDA_TECNICA.md).

La campanita de gestión reúne comprobantes, solicitudes de atención humana y
stock bajo/agotado, con lectura por usuario en este navegador. Pendientes y
Todas distinguen el estado operativo de la lectura. Los datos se comparten
con los avisos del panel; alcance y límites en
[operación de pedidos](../../docs/OPERACION_PEDIDOS.md#centro-de-notificaciones).

En el menú, los productos de **Dips Extra** se agregan completos, sin opciones
para retirar ingredientes ni notas de personalización, aunque la API entregue
ingredientes quitables. Las demás categorías conservan sus opciones vigentes.
Esta regla de presentación no modifica recetas ni datos de la base.

## Fotografías de salsas

Los productos existentes Alioli, Barbacoa, Mayonesa, Ketchup y Mostaza de
**Dips Extra** usan sus archivos homónimos en `public/images/salsas/*.webp`
cuando la API no trae `imagen_url`. La asociación compartida está en
`src/shared/store/productImages.js`: una foto explícita de la API tiene prioridad.
No modifica IDs, precios, recetas, stock ni la base; depende del nombre y categoría
vigentes del producto. Menú y catálogo consumen la misma resolución de fotos.

Son recortes de 138 × 135 px de la captura original provista `salsas monu.png`
(402 × 798 px), guardados como WebP sin pérdida, sin texto y sin redimensionar.
El menú presenta Dips Extra en tarjetas horizontales con miniatura de 96 px de
ancho, proporcionada y sin ampliación, con el botón de agregar fuera de la foto.
El catálogo conserva sus miniaturas. Los recursos se incluyen en ambos portales
y la asociación se reconstruye al recargar. El encuadre no recupera detalle
perdido: para mejorar la nitidez, especialmente en pantallas de doble densidad,
se necesitan fotografías originales de mayor resolución que esta captura.

## Verificación

```powershell
npm run lint
npm run build
npm run test:portales
```

El lint usa **oxlint** (`.oxlintrc.json`) y build genera `dist/`. No existe
`npm test` ni una suite end-to-end de navegador en CI. `test:portales` usa Node,
renderizado React y un servidor HTTP local para comprobar separación de rutas y
el proxy de Pages; no requiere base de datos. Para cambios de interfaz,
comprobar el recorrido, errores, permisos, teclado y responsive en navegador.

No editar `dist/`. La arquitectura y convenciones están
en [ARQUITECTURA.md](../../docs/ARQUITECTURA.md) y
[CLEAN_CODE.md](../../docs/CLEAN_CODE.md).
