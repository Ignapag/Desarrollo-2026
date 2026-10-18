# Frontend

Seguí [AGENTS raíz](../../AGENTS.md). Este es el único frontend del repositorio.
Consultá [arquitectura](../../docs/ARQUITECTURA.md) y
[código limpio](../../docs/CLEAN_CODE.md) según la tarea.

## Skill obligatoria

Todo trabajo sobre este frontend debe utilizar
[`ui-ux-pro-max`](../../.agents/skills/ui-ux-pro-max/SKILL.md), según la regla de
[AGENTS raíz](../../AGENTS.md). Leé la skill antes de analizar, diseñar,
implementar, refactorizar, corregir o revisar el frontend y aplicá las guías
pertinentes al cambio. Usá los recursos de la copia local y respetá los tokens,
componentes y decisiones visuales existentes de Monu Burger.

## Flujo activo

- `index.html` → `src/main.jsx` → `src/App.jsx`.
- `auth/AuthContext.jsx`: sesión contra la API, roles y cookie.
- `shared/api/http.js`: cliente HTTP con `credentials: 'include'` y errores.
- `shared/store/DataContext.jsx`: consultas y acciones de varias capacidades.
- `ordering` (menú, carrito `CartDrawer`), `fulfillment`, `kitchen`, `inventory`,
  `management`: recorridos actuales; cada pantalla vive en su capacidad.
- `index.css`: estilos y tokens activos con Tailwind 4 (`@theme`, sin config JS).

Todo `src/` es JSX alcanzable desde `main.jsx`. La integración TSX anterior y las
vistas de registro/recuperación se retiraron; están en el historial de Git.

Preferí la capacidad dueña y el cliente HTTP existente. El servidor decide
precios, disponibilidad y autorización. Conservá el manejo de carga, errores,
rollback optimista y reconciliación. No simular éxito si la API falló.
Para estados, cobros y reparto, seguir [operación de pedidos](../../docs/OPERACION_PEDIDOS.md):
las acciones físicas se registran en la API; conservar versiones y UUID financieros
en reintentos, y descartar GET anteriores a una mutación.

`App.jsx` redirige `/register` y `/recover-password` a login: no hay vistas ni
endpoints para esas funciones. Algunas pantallas administrativas contienen datos demostrativos.
No inventar endpoints ni presentar esas vistas como integración real completa.

## Verificar

Desde esta carpeta:

```powershell
npm run lint
npm run build
```

El lint usa **oxlint** (`.oxlintrc.json`), el build usa Vite. No existe `npm test`.
Para UI verificar el recorrido afectado en navegador, teclado y responsive,
indicando si no pudo comprobarse.

`npm ci` prepara dependencias; no es un paso por defecto antes de cada check.
No editar `dist/` ni el lockfile a mano. `VITE_*` es público. Inicio y proxy en [desarrollo](../../docs/DESARROLLO.md).
