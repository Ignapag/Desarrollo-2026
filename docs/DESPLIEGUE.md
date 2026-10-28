# Despliegue de clientes y personal en Cloudflare Pages

Un único frontend en `App/frontend` produce dos variantes. Cada proyecto de
Cloudflare Pages usa el mismo repositorio y una dirección distinta. La selección
se hace al compilar, no por un parámetro que pueda cambiar el visitante.

| Configuración | Clientes | Personal |
| --- | --- | --- |
| Proyecto | `monu-burger-clientes-desarrollo` | `monu-burger-desarrollo` |
| Dirección | `https://monu-burger-clientes-desarrollo.pages.dev` | `https://monu-burger-desarrollo.pages.dev` |
| Root directory | `App/frontend` | `App/frontend` |
| Build command | `npm run build:clientes` | `npm run build:personal` |
| Build output directory | `dist` | `dist` |
| Node.js | 22 | 22 |
| Entrada | Menú y carrito sin cuenta | Login; después gestión o reparto según el rol |

Los dos proyectos usan este repositorio `Desarrollo-2026` y consultan el backend
de Desarrollo en Render: `https://monu-burger-desarrollo.onrender.com`.
`API_ORIGIN` permite configurar otro destino en Pages. No utilizar el backend
de Seminario como destino de estos portales.

## Qué está preparado en el código

- En clientes solo se registran las rutas del menú; no se consulta la sesión ni
  se ofrecen login o gestión. El pedido continúa por WhatsApp o por el chat
  académico cuando está habilitado.
- En personal se registran login, dashboard y reparto con sus guardas. No se
  registra el menú público ni el checkout. Las cuentas históricas de clientes
  no permiten iniciar una sesión del personal.
- Las pantallas internas se cargan bajo demanda. Ocultar rutas en React no es
  una autorización de API: el backend sigue validando cookies y roles.
- `functions/api/[[path]].js` reenvía `/api/*` a Render desde el mismo dominio de
  Pages. Preserva estados HTTP, JSON, cuerpos, adjuntos y cookie HttpOnly; evita
  caché y no sigue redirecciones del backend hacia otro origen con credenciales.
- `public/_routes.json` limita la ejecución de Pages Functions a `/api` y
  `/api/*`. Los archivos estáticos se sirven normalmente y `public/_redirects`
  conserva el fallback de React Router para recargas de rutas.

## Configurar Pages

En **Workers & Pages**, abrir el proyecto actual y configurar sus builds como
indica la columna Personal. Crear un segundo proyecto de Pages, conectado al
mismo repositorio y rama, con la configuración de Clientes. Configurar las
variables tanto en producción como en preview cuando se utilicen ambos entornos.

1. Usar `NODE_VERSION=22` si el entorno de build no lo selecciona por defecto.
2. Dejar `VITE_API_URL` sin definir o vacío en ambos proyectos para usar `/api`
   mediante Pages Functions. Si el proyecto actual lo tiene apuntando directamente
   a Render, retirarlo de la configuración de Pages y volver a compilar. No es
   necesario modificar `App/.env`.
   El personal deberá iniciar sesión otra vez: la cookie del dominio de Render
   no se traslada automáticamente al dominio de Pages.
3. Dejar `API_ORIGIN` sin definir para usar el backend de Desarrollo predeterminado,
   o definirla como `https://monu-burger-desarrollo.onrender.com`, sin `/api` ni
   rutas. **Si se copió la URL de Seminario en esta variable, actualizarla**:
   tiene prioridad sobre el destino del código. Es una variable de ejecución
   de Pages Functions, no solo del build. Volver a desplegar ambos proyectos.
   Es una URL de servidor, no un token. La función ignora destinos enviados
   por el visitante.
4. Usar integración Git de Pages para desplegar el repositorio completo: la carpeta
   `functions` está fuera de `dist` y debe incluirse. Una carga manual de solo
   `dist` no instala el proxy de la API.

El backend conserva `ENTORNO=produccion`, cookies Secure/HttpOnly y las variables
de Meta/Gemini ya configuradas. No copiar `DATABASE_URL`, `JWT_SECRET`, tokens ni
otras credenciales a Pages o a variables `VITE_*`. Conservar la lista explícita
de orígenes permitidos en Render. Configurar allí:

```text
ORIGENES_PERMITIDOS=https://monu-burger-desarrollo.pages.dev,https://monu-burger-clientes-desarrollo.pages.dev
```

Esta variable reemplaza los valores predeterminados del código. Si se copiaron
las variables de Seminario, actualizarla y reiniciar Render. Es necesaria también
con el proxy: el chat valida la cabecera `Origin` original antes de abrir sesión.
Conservar `X-Chat-Demo` y no permitir orígenes mediante comodines.

## Orden y validación de la publicación

La [activación pública del chat académico](WHATSAPP_DESARROLLO.md#publicación-autorizada-en-la-base-compartida)
requiere la autorización correspondiente a la base que utiliza Desarrollo; la
autorización histórica de Seminario no verifica la configuración del nuevo servicio.
Se controla mediante el parámetro
persistido `chat_demo_publico` y el arranque existente
`python -m scripts.serve --migrar`: conserva producción, credenciales privadas y
las reglas operativas. Con WhatsApp simulado, el worker integrado sólo procesa
el canal web; con WhatsApp real conserva ambos canales y nunca envía la demo a Meta.
No cargar seed ni ejecutar tests sobre esa base para activar el chat.

Si se conservó el parámetro `chat_demo_publico` de la copia, sus orígenes de
Seminario no incluyen los de Desarrollo. `ORIGENES_PERMITIDOS` permite agregar
los nuevos sitios sin modificar ese dato compartido. Si la nueva base no tiene
el parámetro, revisar la habilitación con su propietario; el cambio de URL no
activa el chat ni configura Gemini. No desactivar las guardas de autorización.

Antes de habilitar compras, coordinar la migración 015 y actualizar API y worker
en Render como indica la [guía de WhatsApp](WHATSAPP_DESARROLLO.md#identidad-comercial-y-vinculación).
No ejecutar seed ni limpiezas en la base compartida. La autorización a preparar
la configuración no sustituye el acceso a las cuentas de hosting.

Desde `App/frontend`, con dependencias preparadas:

```powershell
npm run test:portales
npm run lint
npm run build:clientes
npm run build:personal
```

Cada build escribe `dist`; no mezclar archivos de variantes anteriores ni editar
artefactos generados. `npm run build` conserva el recorrido completo para desarrollo.
Para ver una variante local contra la API local:

```powershell
npm run dev -- --mode clientes
# O bien, en otra terminal y un puerto libre:
npm run dev -- --mode personal
```

`VITE_PORTAL=clientes|personal|completo` permite seleccionar la variante con los
comandos genéricos. Los modos explícitos de los comandos `build:clientes` y
`build:personal` tienen prioridad y un valor desconocido hace fallar el build.

Después de publicar, comprobar en cada dominio:

- `/api/salud` responde JSON del backend y no el HTML del frontend.
- `/api/chat-demo/config` informa si el canal está habilitado y Gemini configurado.
  El POST `/api/chat-demo/sesion` desde el dominio cliente conserva su `Origin`
  y `X-Chat-Demo: 1`, responde `200` y entrega la cookie HttpOnly. Un GET de
  configuración exitoso por sí solo no demuestra que se acepte el origen del POST.
- Clientes: `/` lleva al menú; `/login`, `/dashboard/orders` y `/delivery` no
  muestran pantallas internas. Carrito, personalizaciones y WhatsApp funcionan
  en una ventana privada sin sesión.
- Personal: `/` lleva al login; iniciar sesión y recargar `/dashboard/orders`
  conserva la sesión. Logout la cierra. Cada rol mantiene sus permisos y el
  repartidor solo consulta sus envíos asignados. `/menu` no abre el checkout.
- Mensajes reales repetidos crean un solo pedido y la recompra permite otro.
  Revisar también transferencia, comprobantes y notas en cocina.
- Teclado, móvil y errores de conexión se comprueban en navegador. Las pruebas
  de renderizado y los builds locales no demuestran que Pages Functions, el
  login ni el intercambio real con Meta ya estén desplegados o funcionando.

La comprobación local no publica los proyectos ni cambia la configuración de
Cloudflare o Render. La comprobación histórica del 20/10/2026 corresponde a los
dominios de Seminario `monu-burger-clientes.pages.dev` y `monu-burger.pages.dev`,
no a los dos nuevos dominios de Desarrollo. En esa fecha se comprobaron
el bundle cliente con chat y su proxy `/api/chat-demo`. La sesión desde el origen
exacto de clientes respondió `200` después de autorizar los dominios de Pages.
Se verificaron mediante HTTP Gemini real, un pedido persistido y su modificación
**Sin Tomate**. Esto no sustituye una revisión visual interactiva en navegador.

Referencias oficiales: [configuración de builds](https://developers.cloudflare.com/pages/configuration/build-configuration/),
[Pages Functions](https://developers.cloudflare.com/pages/functions/get-started/) y
[rutas de Functions](https://developers.cloudflare.com/pages/functions/routing/).
