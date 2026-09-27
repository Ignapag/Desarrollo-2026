# 🍔 Monu Burger - Frontend

Esta carpeta contiene la interfaz gráfica y la experiencia de usuario (Frontend) de **Monu Burger**, desarrollada en React con Vite y Tailwind CSS v4.

## 🎨 ¿Qué se hizo? (Estado de la UI/UX)
El maquetado visual, la interactividad de la interfaz y el diseño responsivo ya están **100% finalizados y listos para usar**. Se diseñaron las siguientes partes:

- **Vistas del Cliente:** Menú interactivo con buscador y categorías. Carrito de compras deslizable completamente funcional (con suma/resta de cantidades).
- **Autenticación:** Pantalla de Login con diseño retro-vintage, y pantallas preparadas para Registro y Recuperación de Contraseña.
- **Panel Administrativo (Dashboard):** Panel de Control con gráficos (Recharts) y resúmenes de ventas, panel de Inventario, Directorio de Clientes y Control de Acceso.
- **Módulo Operativo:** Vista de Pedidos tipo Kanban (Arrastrar y soltar visual) y pantalla de Cocina (KDS).
- **Módulo de Repartidor:** Interfaz pensada específicamente para celular (deslizable hacia abajo, sin cortes laterales) con listado de pedidos pendientes y entregados.
- **Detalles técnicos:** Tablas responsivas, protección de rutas y diseño centralizado mediante variables CSS (CSS-first) de Tailwind v4.

---

## 🔌 ¿Qué hay que conectar? (Guía para el Equipo de Backend)

La estructura está armada para que la integración sea lo más limpia posible. **No es necesario modificar los componentes visuales (`.jsx`)**. Toda la inyección de datos reales debe hacerse modificando los simuladores ubicados en los archivos de la carpeta `context/`.

### 1. Autenticación (`src/context/AuthContext.jsx`)
*Ideal para: Tomás (Autenticación y Roles)*
- **Estado actual:** El proyecto usa un "simulador local" que acepta cualquier correo (si pones "admin", te hace admin, etc.). 
- **Qué hacer:** Reemplazar el interior de la función `login` por una llamada `fetch` o `axios.post('/api/login')` hacia la base de datos real. Esa llamada debe retornar un token JWT y el rol del usuario para setearlo en la app. También hay que conectar las funciones de `register` y las de recuperación de clave.

### 2. Base de Datos / Pedidos (`src/context/DataContext.jsx`)
*Ideal para: Ignacio / José (Base de Datos, Reportes y Lógica)*
- **Estado actual:** La app arranca con un `initialState` que tiene arreglos de hamburguesas, clientes y pedidos de prueba (mock data).
- **Qué hacer:** 
  1. Limpiar esos arreglos de prueba para que arranquen vacíos `[]`.
  2. Agregar un `useEffect` en el `DataProvider` que haga peticiones `GET` a los endpoints de la API (ej: `/api/menu`, `/api/orders`) para popular la pantalla apenas el usuario ingresa.
  3. Modificar las acciones como `PLACE_ORDER` o `UPDATE_ORDER_STATUS`. En lugar de cambiar la pantalla de inmediato, primero deben hacer un `POST/PUT` al servidor. Si el servidor dice "OK", ahí recién se actualiza el estado de React.

### 3. Pagos
*Ideal para: Nicolás*
- **Qué hacer:** Enganchar el botón de "Confirmar Pedido" del carrito con la lógica o pasarela de MercadoPago / transferencia que requiera el sistema.