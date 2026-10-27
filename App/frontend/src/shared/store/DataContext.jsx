import { createContext, useContext, useReducer, useEffect } from 'react';

import { useState, useCallback, useRef, useLayoutEffect, useMemo } from 'react';
import { can } from '../../auth/permissions';
import { useAuth } from '../../auth/AuthContext';
import { apiFetch } from '../api/http';
import { portal } from '../portal';
import { mapOrder, createFreshnessFence, ordersPath, confirmedOrder } from '../../fulfillment/orderModel';
import { createOrderCommands } from '../../fulfillment/orderCommands';

// ==========================================
// Los datos operativos se consultan en la API; no hay personas ni stock ficticios.
// ==========================================
const initialState = {
  catalog: [],
  catalogStatus: 'loading',
  catalogError: null,
  cart: [],
  orders: [],
  ordersOwner: null,
  ordersStatus: 'loading',
  ordersError: null,
  inventory: [],
  inventoryOwner: null,
  inventoryStatus: 'idle',
  inventoryError: null,
};

function mapProduct(product) {
  return {
    id: product.id,
    categoryId: product.categoria_id,
    name: product.nombre,
    description: product.descripcion || '',
    category: product.categoria,
    price: Number(product.precio_base),
    image: product.imagen_url,
    variants: (product.variantes || []).map((variant) => ({
      name: variant.nombre,
      price: Number(variant.precio),
      available: variant.disponible ?? true,
    })),
    active: product.activo,
    available: product.disponible,
    removableIngredients: product.ingredientes_quitables || [],
  };
}

function mapInventory(item) {
  return {
    id: item.id,
    name: item.nombre,
    category: item.unidad_medida,
    stock: Number(item.cantidad_actual),
    min: Number(item.umbral_minimo),
    status: item.nivel === 'NORMAL' ? 'estable' : 'critico',
  };
}

function dataReducer(state, action) {
  switch (action.type) {
    case 'SYNC_ORDERS':
      return { ...state, orders: action.payload, ordersOwner: action.owner, ordersStatus: 'ready', ordersError: null };
    case 'ORDERS_ERROR':
      return { ...state, ...(action.unauthorized && { orders: [] }), ordersStatus: 'error', ordersError: action.payload };
    case 'UPSERT_ORDER':
      return { ...state, ordersOwner: action.owner, orders: state.orders.some((o) => o.id === action.payload.id)
        ? state.orders.map((o) => o.id === action.payload.id ? action.payload : o) : [action.payload, ...state.orders] };
    case 'RESET_PRIVATE_DATA':
      return { ...state, orders: [], ordersOwner: null, ordersStatus: 'loading', ordersError: null, inventory: [], inventoryStatus: 'idle', inventoryError: null };
    case 'SYNC_CATALOG':
      return { ...state, catalog: action.payload, catalogStatus: 'ready', catalogError: null };
    case 'CATALOG_LOADING':
      return { ...state, catalogStatus: 'loading', catalogError: null };
    case 'CATALOG_ERROR':
      return { ...state, catalogStatus: 'error', catalogError: action.payload };
    case 'SYNC_INVENTORY':
      return { ...state, inventory: action.payload, inventoryOwner: action.owner, inventoryStatus: 'ready', inventoryError: null };
    case 'INVENTORY_LOADING':
      return { ...state, inventoryOwner: action.owner, inventoryStatus: 'loading', inventoryError: null };
    case 'INVENTORY_ERROR':
      return { ...state, ...(action.unauthorized && { inventory: [] }), inventoryOwner: action.owner, inventoryStatus: 'error', inventoryError: action.payload };
    case 'ADD_TO_CART': {
      const existingIndex = state.cart.findIndex(item => item.id === action.payload.id);
      if (existingIndex >= 0) {
        const newCart = [...state.cart];
        newCart[existingIndex] = {
          ...newCart[existingIndex],
          quantity: newCart[existingIndex].quantity + action.payload.quantity
        };
        return { ...state, cart: newCart };
      }
      return { ...state, cart: [...state.cart, action.payload] };
    }
    case 'UPDATE_CART_QUANTITY': {
      const { index, delta } = action.payload;
      const newCart = [...state.cart];
      const newQuantity = newCart[index].quantity + delta;
      
      if (newQuantity <= 0) {
        newCart.splice(index, 1);
      } else {
        newCart[index] = { ...newCart[index], quantity: newQuantity };
      }
      return { ...state, cart: newCart };
    }
    case 'REMOVE_FROM_CART':
      return { ...state, cart: state.cart.filter((_, i) => i !== action.payload) };
    case 'CLEAR_CART':
      return { ...state, cart: [] };
    
    case 'PLACE_ORDER':
      return {
        ...state,
        orders: [action.payload, ...state.orders],
        ordersOwner: action.owner,
        cart: []
      }
    case 'ADD_CATALOG_ITEM':
      return { ...state, catalog: [action.payload, ...state.catalog] };
    case 'DELETE_CATALOG_ITEM':
      return { ...state, catalog: state.catalog.filter(p => p.id !== action.payload) };
    case 'ADD_INVENTORY_ITEM':
      return {
        ...state,
        inventory: [{ ...action.payload }, ...state.inventory], inventoryOwner: action.owner,
      }
    case 'UPDATE_INVENTORY_STOCK': {
      const { id, delta } = action.payload;
      return {
        ...state,
        inventory: state.inventory.map(item => {
          if (item.id === id) {
            const newStock = Math.max(0, item.stock + delta); // No permitir stock negativo
            const newStatus = newStock <= item.min ? 'critico' : 'estable';
            return { ...item, stock: newStock, status: newStatus };
          }
          return item;
        })
      };
    }
    case 'CONFIRM_INVENTORY_STOCK':
      return { ...state, inventory: state.inventory.map((item) => item.id === action.id ? { ...item, stock: action.stock, status: action.stock <= item.min ? 'critico' : 'estable' } : item) };
    default:
      return state;
  }
}

const DataContext = createContext(null);

export function DataProvider({ children }) {
  const [state, dispatch] = useReducer(dataReducer, initialState);
  const [loading, setLoading] = useState(false);
  const { user, refreshSession } = useAuth();
  const userRef = useRef(user);
  const ordersRequestRef = useRef(null);
  const freshnessRef = useRef(createFreshnessFence());
  const commands = createOrderCommands(apiFetch);
  const catalogRequest = useRef(null);
  const inventoryRequest = useRef(null);
  const catalogLoadedAt = useRef(0);
  const inventoryLoadedAt = useRef(0);
  const catalogFence = useRef(createFreshnessFence());
  const inventoryFence = useRef(createFreshnessFence());
  const customerCache = useRef(new Map());
  const orderSubscribers = useRef(0);
  const lastOrdersRead = useRef(0);
  const operationsRef = useRef(new Map());
  const [operations, setOperations] = useState({ owner: user, entries: [] });
  const projectOrder = useCallback((order) => {
    const entry = operations.owner === user && operations.entries.find((item) => item.id === order.id && item.status === 'pending');
    if (entry?.preview) return entry.preview;
    const confirmed = state.ordersOwner === user && state.orders.find((item) => item.id === order.id);
    return confirmed && confirmed.version > order.version ? confirmed : order;
  }, [operations, user, state.orders, state.ordersOwner]);
  const visibleOrders = useMemo(() => {
    if (!user) return [];
    const orders = state.ordersOwner === user ? state.orders : [];
    const previews = operations.owner === user ? operations.entries.filter((entry) => entry.status === 'pending' && entry.preview) : [];
    if (!previews.length) return orders;
    return [...orders.map(projectOrder), ...previews.filter((entry) => !orders.some((order) => order.id === entry.id)).map((entry) => entry.preview)];
  }, [state.orders, state.ordersOwner, operations, projectOrder, user]);

  useLayoutEffect(() => {
    freshnessRef.current = createFreshnessFence();
    // Las escrituras pendientes de otra sesión conservan su propia barrera.
    catalogFence.current = createFreshnessFence();
    inventoryFence.current = createFreshnessFence();
    userRef.current = user;
    catalogRequest.current = null;
    inventoryRequest.current = null;
    catalogLoadedAt.current = 0;
    inventoryLoadedAt.current = 0;
    lastOrdersRead.current = 0;
    customerCache.current.clear();
    operationsRef.current = new Map();
    return () => {
      userRef.current = null;
      for (const entry of operationsRef.current.values()) clearTimeout(entry.timer);
    };
  }, [user]);

  const refreshOrders = useCallback((signal, force = false) => {
    if (!user || (!can(user, 'pedidos.ver') && user.backendRole !== 'CLIENTE') || userRef.current !== user) return Promise.resolve();
    if (!force && ordersRequestRef.current?.owner === user && !ordersRequestRef.current.signal?.aborted) return ordersRequestRef.current.request;
    const token = freshnessRef.current.read();
    const request = apiFetch(ordersPath({ activos: true }), { signal })
      .then((orders) => {
        if (userRef.current === user && !signal?.aborted && freshnessRef.current.accepts(token)) {
          dispatch({ type: 'SYNC_ORDERS', payload: orders.map(mapOrder), owner: user });
          lastOrdersRead.current = Date.now();
        }
      })
      .catch((error) => {
        if (userRef.current === user && !signal?.aborted && freshnessRef.current.accepts(token)) {
          const unauthorized = [401, 403].includes(error.status);
          if (unauthorized) void refreshSession?.();
          dispatch({ type: 'ORDERS_ERROR', unauthorized, payload: `No se pudieron actualizar los pedidos.${unauthorized ? '' : ' Se conserva la última información.'} ${error.message}` });
        }
        throw error;
      })
      .finally(() => {
        if (ordersRequestRef.current?.request === request) ordersRequestRef.current = null;
      });
    ordersRequestRef.current = { owner: user, signal, request };
    return request;
  }, [user, refreshSession]);

  const refreshCatalog = useCallback((signal, force = false) => {
    if (!force && catalogRequest.current?.owner === user && !catalogRequest.current.signal?.aborted) return catalogRequest.current.promise;
    if (!force && Date.now() - catalogLoadedAt.current < 30000) return Promise.resolve();
    if (!catalogLoadedAt.current) dispatch({ type: 'CATALOG_LOADING' });
    const entry = { owner: user, signal };
    const token = catalogFence.current.read();
    entry.promise = apiFetch('/api/productos', { signal }).then((products) => {
      if (!signal?.aborted && userRef.current === user && catalogRequest.current === entry && catalogFence.current.accepts(token)) {
        catalogLoadedAt.current = Date.now();
        dispatch({ type: 'SYNC_CATALOG', payload: products.map(mapProduct) });
      }
    }).catch((error) => {
      if (!signal?.aborted && userRef.current === user && catalogRequest.current === entry && catalogFence.current.accepts(token)) {
        catalogLoadedAt.current = 0;
        dispatch({ type: 'CATALOG_ERROR', payload: 'No pudimos cargar el menú. Intentá nuevamente.' });
      }
      throw error;
    }).finally(() => { if (catalogRequest.current === entry) catalogRequest.current = null; });
    catalogRequest.current = entry;
    return entry.promise;
  }, [user]);

  const refreshInventory = useCallback((signal, force = false) => {
    if (!can(user, 'stock.ver') || userRef.current !== user) return Promise.resolve();
    if (!force && inventoryRequest.current?.owner === user && !inventoryRequest.current.signal?.aborted) return inventoryRequest.current.promise;
    if (!force && Date.now() - inventoryLoadedAt.current < 30000) return Promise.resolve();
    if (!inventoryLoadedAt.current) dispatch({ type: 'INVENTORY_LOADING', owner: user });
    const entry = { owner: user, signal };
    const token = inventoryFence.current.read();
    entry.promise = apiFetch('/api/stock/ingredientes?activo=true', { signal }).then((inventory) => {
      if (!signal?.aborted && userRef.current === user && inventoryRequest.current === entry && inventoryFence.current.accepts(token)) {
        inventoryLoadedAt.current = Date.now();
        dispatch({ type: 'SYNC_INVENTORY', payload: inventory.map(mapInventory), owner: user });
      }
    }).catch((error) => {
      if (!signal?.aborted && userRef.current === user && inventoryRequest.current === entry && inventoryFence.current.accepts(token)) {
        inventoryLoadedAt.current = 0;
        dispatch({ type: 'INVENTORY_ERROR', payload: error.message, owner: user, unauthorized: [401, 403].includes(error.status) });
        if ([401, 403].includes(error.status)) void refreshSession?.();
      }
      throw error;
    }).finally(() => { if (inventoryRequest.current === entry) inventoryRequest.current = null; });
    inventoryRequest.current = entry;
    return entry.promise;
  }, [user, refreshSession]);

  const cachedCustomers = useCallback((path) => {
    if (!can(user, 'clientes.ver') || userRef.current !== user) return null;
    const entry = customerCache.current.get(path);
    return entry?.owner === user && Date.now() - entry.time < 30000 ? entry.value : null;
  }, [user]);

  const getCustomers = useCallback((path, signal, force = false) => {
    if (!can(user, 'clientes.ver') || userRef.current !== user) return Promise.reject(new Error('No tenés acceso a clientes.'));
    const previous = customerCache.current.get(path);
    if (!force && previous?.owner === user) {
      if (previous.promise && !previous.signal?.aborted) return previous.promise;
      if (previous.value && Date.now() - previous.time < 30000) return Promise.resolve(previous.value);
    }
    const entry = { owner: user, signal, time: 0 };
    entry.promise = apiFetch(path, { signal }).then((value) => {
      if (!signal?.aborted && userRef.current === user && customerCache.current.get(path) === entry) {
        entry.value = value;
        entry.time = Date.now();
        entry.promise = null;
        // La caché es de navegación de esta sesión, no un directorio ilimitado.
        if (customerCache.current.size > 20) customerCache.current.delete(customerCache.current.keys().next().value);
      }
      return value;
    }).catch((error) => {
      if (customerCache.current.get(path) === entry) customerCache.current.delete(path);
      if (userRef.current === user && [401, 403].includes(error.status)) customerCache.current.clear();
      throw error;
    });
    customerCache.current.set(path, entry);
    return entry.promise;
  }, [user]);

  const watchOrders = useCallback(() => {
    orderSubscribers.current += 1;
    if (lastOrdersRead.current && Date.now() - lastOrdersRead.current > 3000) void refreshOrders().catch(() => undefined);
    return () => { orderSubscribers.current -= 1; };
  }, [refreshOrders]);

  const runOrderMutation = async (operation) => {
    if (!user || userRef.current !== user) throw new Error('La sesión cambió. Volvé a ingresar antes de continuar.');
    const owner = user;
    const fence = freshnessRef.current;
    let confirmed = null;
    fence.beginMutation();
    try {
      const result = await operation();
      confirmed = confirmedOrder(result);
      if (userRef.current === owner && confirmed) {
        dispatch({ type: 'UPSERT_ORDER', payload: mapOrder(confirmed), owner });
      }
      return result;
    } finally {
      fence.endMutation();
      if (userRef.current === owner && !confirmed) {
        // El error queda visible en el tablero; no convierte un comando confirmado en un fallo.
        void refreshOrders(undefined, true).catch(() => undefined);
      }
    }
  };

  const publishOperations = () => {
    if (userRef.current !== user) return;
    setOperations({ owner: user, entries: [...operationsRef.current.values()].map(({ id, number, status, message, preview, silent }) => ({ id, number, status, message, preview, silent })) });
  };

  const orderOperationPending = (id) => userRef.current === user && operationsRef.current.get(id)?.status === 'pending';

  const dismissOrderOperation = (id) => {
    if (orderOperationPending(id) || userRef.current !== user) return;
    clearTimeout(operationsRef.current.get(id)?.timer);
    operationsRef.current.delete(id);
    publishOperations();
  };

  // La operación vive en el provider, no en el modal que la inició.
  const startOrderOperation = ({ id, number, operation, optimisticOrder, success = 'Pedido actualizado.', onSuccess, onError }) => {
    if (!user || userRef.current !== user || orderOperationPending(id)) return false;
    clearTimeout(operationsRef.current.get(id)?.timer);
    // La proyección sólo cambia la vista. La respuesta de la API conserva la autoridad
    // sobre versión, dinero, stock y fechas; un fallo retira la proyección de inmediato.
    const preview = confirmedOrder(optimisticOrder, id) ? mapOrder(optimisticOrder) : null;
    const entry = { id, number, status: 'pending', message: '', preview, silent: Boolean(preview) };
    operationsRef.current.set(id, entry);
    publishOperations();
    void runOrderMutation(async () => {
      const result = await operation(() => userRef.current === user);
      if (userRef.current !== user) return result;
      if (!result || typeof result !== 'object' || !Object.keys(result).length) throw new Error('No se pudo confirmar la acción: respuesta incompleta.');
      // Reparto y adaptadores anteriores pueden devolver sólo el movimiento.
      const confirmed = confirmedOrder(result, id) || confirmedOrder(await apiFetch(`/api/pedidos/${id}`), id);
      if (!confirmed) throw new Error('No se pudo confirmar el pedido: respuesta incompleta.');
      return confirmed;
    }).then((result) => {
      if (userRef.current !== user || operationsRef.current.get(id) !== entry) return;
      entry.status = 'success';
      entry.message = success;
      publishOperations();
      onSuccess?.(result);
      entry.timer = setTimeout(() => {
        if (userRef.current === user && operationsRef.current.get(id) === entry) dismissOrderOperation(id);
      }, 4000);
    }).catch((error) => {
      if (userRef.current !== user || operationsRef.current.get(id) !== entry) return;
      entry.status = 'error';
      entry.message = `${error.message} No pudimos confirmar el estado final. Revisá el pedido antes de reintentar.`;
      publishOperations();
      onError?.(entry.message);
    });
    return true;
  };

  const refreshData = useCallback(async (signal) => {
    // También se llama después de escrituras externas al store, como la revisión
    // de WhatsApp: ningún GET iniciado antes de esa revisión puede publicarse.
    freshnessRef.current.invalidate();
    setLoading(true);
    catalogLoadedAt.current = 0;
    inventoryLoadedAt.current = 0;
    customerCache.current.clear();
    try {
      const tasks = [];
      if ((!user && portal.clientes) || user?.role === 'cliente') tasks.push(refreshCatalog(signal, true));
      if (user) tasks.push(refreshOrders(signal, true));
      const results = await Promise.allSettled(tasks);
      const failure = results.find((result) => result.status === 'rejected');
      if (failure) throw failure.reason;
    } finally {
      if (userRef.current === user && !signal?.aborted) setLoading(false);
    }
  }, [user, refreshOrders, refreshCatalog]);

  useEffect(() => {
    const controller = new AbortController();
    // Sólo datos iniciales necesarios; las pantallas piden sus recursos al abrirse.
    Promise.resolve().then(() => {
      if (controller.signal.aborted) return undefined;
      const tasks = [];
      if ((!user && portal.clientes) || user?.role === 'cliente') tasks.push(refreshCatalog(controller.signal));
      if (user) tasks.push(refreshOrders(controller.signal));
      return Promise.allSettled(tasks);
    }).catch(() => undefined);
    return () => {
      controller.abort();
      dispatch({ type: 'RESET_PRIVATE_DATA' });
    };
  }, [user, refreshCatalog, refreshOrders]);

  useEffect(() => {
    if (!['EMPLEADO', 'ADMINISTRADOR', 'DUENIO', 'REPARTIDOR'].includes(user?.backendRole)) return undefined;
    let controller = null;
    const updateOrders = async () => {
      if (document.hidden || controller || orderSubscribers.current === 0) return;
      controller = new AbortController();
      try {
        await refreshOrders(controller.signal);
      } catch {
        // refreshOrders publica el error y conserva el último tablero disponible.
      } finally {
        controller = null;
      }
    };
    const onVisibilityChange = () => {
      if (document.hidden) controller?.abort();
      else void updateOrders();
    };
    const timer = window.setInterval(updateOrders, 8000);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      controller?.abort();
    };
  }, [user?.id, user?.backendRole, refreshOrders]);

  const runResourceMutation = async (kind, operation, permission) => {
    if (!user || userRef.current !== user || !can(user, permission)) throw new Error('La sesión cambió o no tenés acceso a esta operación.');
    const fence = kind === 'catalog' ? catalogFence.current : inventoryFence.current;
    const request = kind === 'catalog' ? catalogRequest : inventoryRequest;
    const refresh = kind === 'catalog' ? refreshCatalog : refreshInventory;
    fence.beginMutation();
    request.current = null;
    try {
      return await operation();
    } finally {
      fence.endMutation();
      if (userRef.current === user) {
        request.current = null;
        // Reconciliar también un fallo incierto sin volver a publicar un GET anterior.
        void refresh(undefined, true).catch(() => undefined);
      }
    }
  };

  const createProduct = async (payload) => runResourceMutation('catalog', async () => {
    const created = await apiFetch('/api/productos', {
      method: 'POST',
      body: JSON.stringify({
        categoria_id: payload.categoryId,
        nombre: payload.name,
        descripcion: payload.description,
        precio_base: payload.price,
        imagen_url: payload.image,
        ingredientes: payload.ingredientes,
        variantes: payload.variantes,
      }),
    });
    if (!Number.isInteger(created?.id) || typeof created.nombre !== 'string' || created.precio_base == null || !Number.isFinite(Number(created.precio_base))) throw new Error('No pudimos confirmar el producto: respuesta incompleta. Actualizá el catálogo antes de reintentar.');
    const product = mapProduct(created);
    if (userRef.current === user) dispatch({ type: 'ADD_CATALOG_ITEM', payload: product });
    return product;
  }, 'productos.gestionar');

  const updateRecipe = async (id, body) => runResourceMutation('catalog', async () => {
    const result = await apiFetch(`/api/productos/${id}/receta`, { method: 'PUT', body: JSON.stringify(body) });
    if (result?.producto_id !== id || !Array.isArray(result.ingredientes) || !Array.isArray(result.variantes) || typeof result.actualizado_en !== 'string') throw new Error('No pudimos confirmar la receta: respuesta incompleta. Consultá su estado antes de reintentar.');
    return result;
  }, 'productos.gestionar');

  const deactivateProduct = async (id) => runResourceMutation('catalog', async () => {
    const result = await apiFetch(`/api/productos/${id}/estado`, {
      method: 'PATCH',
      body: JSON.stringify({ activo: false }),
    });
    if (result?.id !== id || result.activo !== false) throw new Error('No pudimos confirmar la desactivación: respuesta incompleta. Actualizá el catálogo antes de reintentar.');
    if (userRef.current === user) dispatch({ type: 'DELETE_CATALOG_ITEM', payload: id });
  }, 'productos.gestionar');

  const changeOrderStatus = async (id, status, options = {}) => {
    if (!can(user, 'pedidos.cambiar_estado')) throw new Error('No tenés acceso a cambiar el estado.');
    const order = state.orders.find((candidate) => candidate.id === id);
    if (!order) throw new Error('Actualizá el pedido antes de cambiar su estado.');
    return runOrderMutation(() => commands.state(order, { estado: status.toUpperCase(), ...options }, options.motivo));
  };

  const placeOrder = async ({ address, zone, items }) => {
    if (!user || userRef.current !== user) throw new Error('La sesión cambió. Volvé a ingresar antes de continuar.');
    const created = await apiFetch('/api/pedidos', {
      method: 'POST',
      body: JSON.stringify({
        tipo_entrega: 'DELIVERY',
        direccion_nueva: {
          calle: address,
          numero: 'S/N',
          localidad: zone,
        },
        items: items.map((item) => ({
          producto_id: Number(String(item.id).split('-')[0]),
          cantidad: item.quantity,
          variante: item.variant || null,
          aclaraciones: item.notes || null,
        })),
      }),
    });
    const order = mapOrder(created);
    if (userRef.current === user) dispatch({ type: 'PLACE_ORDER', payload: order, owner: user });
    return created;
  };

  const createIngredient = async (payload) => runResourceMutation('inventory', async () => {
    const created = await apiFetch('/api/stock/ingredientes', {
      method: 'POST',
      body: JSON.stringify({
        nombre: payload.name,
        unidad_medida: payload.unit,
        cantidad_actual: Number(payload.stock),
        umbral_minimo: Number(payload.min),
      }),
    });
    if (!Number.isInteger(created?.id) || typeof created.nombre !== 'string' || created.cantidad_actual == null || created.umbral_minimo == null || !Number.isFinite(Number(created.cantidad_actual)) || !Number.isFinite(Number(created.umbral_minimo))) throw new Error('No pudimos confirmar el insumo: respuesta incompleta. Actualizá el inventario antes de reintentar.');
    const item = mapInventory(created);
    if (userRef.current === user) dispatch({ type: 'ADD_INVENTORY_ITEM', payload: item, owner: user });
    return item;
  }, 'stock.gestionar');

  const replenishIngredient = async (id, quantity = 1) => runResourceMutation('inventory', async () => {
    // Actualizacion optimista: Render y Supabase estan en regiones distintas,
    // pero el operador debe ver el cambio apenas toca el boton.
    dispatch({ type: 'UPDATE_INVENTORY_STOCK', payload: { id, delta: quantity } });
    try {
      const result = await apiFetch(`/api/stock/ingredientes/${id}/reposiciones`, {
        method: 'POST',
        body: JSON.stringify({ cantidad: quantity, origen: 'PANEL_WEB' }),
      });
      if (result?.ingrediente_id !== id || !Number.isInteger(result.movimiento_id) || result.saldo_resultante == null || !Number.isFinite(Number(result.saldo_resultante))) throw new Error('No pudimos confirmar la reposición: respuesta incompleta. Consultá el inventario antes de reintentar.');
      if (userRef.current === user) dispatch({ type: 'CONFIRM_INVENTORY_STOCK', id, stock: Number(result.saldo_resultante) });
    } catch (error) {
      if (userRef.current === user) dispatch({ type: 'UPDATE_INVENTORY_STOCK', payload: { id, delta: -quantity } });
      throw error;
    }
  }, 'stock.reponer');

  return (
    <DataContext.Provider value={{
      state: { ...state, orders: visibleOrders,
        inventory: can(user, 'stock.ver') && state.inventoryOwner === user ? state.inventory : [],
        inventoryStatus: can(user, 'stock.ver') && state.inventoryOwner === user ? state.inventoryStatus : 'idle',
        inventoryError: can(user, 'stock.ver') && state.inventoryOwner === user ? state.inventoryError : null,
      },
      dispatch,
      loading,
      refreshData,
      createProduct,
      updateRecipe,
      deactivateProduct,
      changeOrderStatus,
      placeOrder,
      refreshOrders,
      watchOrders,
      refreshCatalog,
      refreshInventory,
      cachedCustomers,
      getCustomers,
      runOrderMutation,
      startOrderOperation,
      orderOperationPending,
      projectOrder,
      dismissOrderOperation,
      orderOperations: operations.owner === user ? operations.entries : [],
      createIngredient,
      replenishIngredient,
    }}>
      {children}
    </DataContext.Provider>
  );
}

export const useData = () => useContext(DataContext);
