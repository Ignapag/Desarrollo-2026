import { createContext, useContext, useReducer, useEffect } from 'react';

import { useState, useCallback, useRef, useLayoutEffect } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { apiFetch } from '../api/http';

// ==========================================
// El cat?logo de compra siempre viene de la API. Los datos de demostraci?n
// restantes solo pertenecen a paneles internos pendientes de integraci?n.
// ==========================================
const initialState = {
  catalog: [],
  catalogStatus: 'loading',
  catalogError: null,
  cart: [],
  orders: [],
  ordersOwner: null,
  inventory: [
    // Proteínas
    { id: 1, name: 'Medallón de Carne', category: 'Proteínas', stock: 0, min: 50, status: 'critico' },
    { id: 2, name: 'Medallón Smash', category: 'Proteínas', stock: 0, min: 50, status: 'critico' },
    { id: 3, name: 'Medallón NotCo', category: 'Proteínas', stock: 0, min: 20, status: 'critico' },
    { id: 4, name: 'Bacon / Panceta', category: 'Proteínas', stock: 0, min: 30, status: 'critico' },
    { id: 5, name: 'Bacon en cubos', category: 'Proteínas', stock: 0, min: 20, status: 'critico' },
    { id: 6, name: 'Huevo', category: 'Proteínas', stock: 0, min: 30, status: 'critico' },
    // Panadería
    { id: 7, name: 'Pan de Hamburguesa', category: 'Panadería', stock: 0, min: 100, status: 'critico' },
    // Lácteos
    { id: 8, name: 'Queso Cheddar', category: 'Lácteos', stock: 0, min: 100, status: 'critico' },
    { id: 9, name: 'Provoleta', category: 'Lácteos', stock: 0, min: 20, status: 'critico' },
    // Verduras
    { id: 10, name: 'Tomate', category: 'Verduras', stock: 0, min: 30, status: 'critico' },
    { id: 11, name: 'Lechuga', category: 'Verduras', stock: 0, min: 30, status: 'critico' },
    { id: 12, name: 'Cebolla cruda', category: 'Verduras', stock: 0, min: 30, status: 'critico' },
    { id: 13, name: 'Cebolla en cubos', category: 'Verduras', stock: 0, min: 20, status: 'critico' },
    { id: 14, name: 'Cebolla caramelizada', category: 'Verduras', stock: 0, min: 20, status: 'critico' },
    { id: 15, name: 'Cebolla crispy', category: 'Verduras', stock: 0, min: 20, status: 'critico' },
    { id: 16, name: 'Rúcula', category: 'Verduras', stock: 0, min: 15, status: 'critico' },
    { id: 17, name: 'Pepinillos', category: 'Verduras', stock: 0, min: 20, status: 'critico' },
    // Aderezos
    { id: 18, name: 'Salsa Monu', category: 'Aderezos', stock: 0, min: 20, status: 'critico' },
    { id: 19, name: 'Alioli', category: 'Aderezos', stock: 0, min: 15, status: 'critico' },
    { id: 20, name: 'Barbacoa', category: 'Aderezos', stock: 0, min: 15, status: 'critico' },
    { id: 21, name: 'Mayonesa', category: 'Aderezos', stock: 0, min: 20, status: 'critico' },
    { id: 22, name: 'Mayonesa ahumada', category: 'Aderezos', stock: 0, min: 15, status: 'critico' },
    { id: 23, name: 'Ketchup', category: 'Aderezos', stock: 0, min: 20, status: 'critico' },
    { id: 24, name: 'Mostaza', category: 'Aderezos', stock: 0, min: 20, status: 'critico' },
    { id: 25, name: 'Salsa Smash', category: 'Aderezos', stock: 0, min: 15, status: 'critico' },
    // Congelados
    { id: 26, name: 'Papas Fritas Congeladas', category: 'Congelados', stock: 0, min: 40, status: 'critico' },
    { id: 27, name: 'Nuggets Congelados', category: 'Congelados', stock: 0, min: 30, status: 'critico' },
    // Bebidas
    { id: 28, name: 'Coca Cola 500ml', category: 'Bebidas', stock: 0, min: 48, status: 'critico' },
    { id: 29, name: 'Sprite 500ml', category: 'Bebidas', stock: 0, min: 24, status: 'critico' },
    { id: 30, name: 'Fanta 500ml', category: 'Bebidas', stock: 0, min: 24, status: 'critico' },
  ],
  customers: [
    { id: 1, name: 'Martina Gómez', phone: '221 555-0102', zone: 'Punta Lara', ordersCount: 2, since: '02 de nov de 2024' },
    { id: 2, name: 'Lucas Fernández', phone: '221 555-0148', zone: 'El Dique', ordersCount: 2, since: '14 de ene de 2025' },
  ]
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
    })),
    active: product.activo,
    available: product.disponible,
    removableIngredients: product.ingredientes_quitables || [],
  };
}

function mapOrder(order) {
  return {
    id: order.id,
    number: order.numero,
    client: order.cliente,
    address: order.tipo_entrega === 'RETIRO' ? 'Retiro en local' : 'Delivery',
    status: order.estado.toLowerCase(),
    total: Number(order.total),
    items: order.items.map((item) => `${item.cantidad}x ${item.nombre_producto}${item.aclaraciones ? ` · ${item.aclaraciones}` : ''}`),
    date: order.creado_en,
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
      return { ...state, orders: action.payload, ordersOwner: action.owner };
    case 'RESET_PRIVATE_DATA':
      return { ...state, orders: [], ordersOwner: null, inventory: initialState.inventory };
    case 'SYNC_CATALOG':
      return { ...state, catalog: action.payload, catalogStatus: 'ready', catalogError: null };
    case 'CATALOG_LOADING':
      return { ...state, catalogStatus: 'loading', catalogError: null };
    case 'CATALOG_ERROR':
      return { ...state, catalogStatus: 'error', catalogError: action.payload };
    case 'SYNC_INVENTORY':
      return { ...state, inventory: action.payload };
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
    
    case 'UPDATE_ORDER_STATUS':
      return {
        ...state,
        orders: state.orders.map(order => 
          order.id === action.payload.id ? { ...order, status: action.payload.status } : order
        )
      };
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
        inventory: [{ id: state.inventory.length + 1, ...action.payload }, ...state.inventory]
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
    default:
      return state;
  }
}

const DataContext = createContext(null);

export function DataProvider({ children }) {
  const [state, dispatch] = useReducer(dataReducer, initialState);
  const [loading, setLoading] = useState(false);
  const { user } = useAuth();
  const userRef = useRef(user);
  const ordersRequestRef = useRef(null);

  useLayoutEffect(() => {
    userRef.current = user;
    return () => { userRef.current = null; };
  }, [user]);

  const refreshOrders = useCallback((signal) => {
    if (!user || userRef.current !== user) return Promise.resolve();
    if (ordersRequestRef.current?.owner === user) return ordersRequestRef.current.request;
    const request = apiFetch('/api/pedidos', { signal })
      .then((orders) => {
        if (userRef.current === user && !signal?.aborted) {
          dispatch({ type: 'SYNC_ORDERS', payload: orders.map(mapOrder), owner: user });
        }
      })
      .finally(() => {
        if (ordersRequestRef.current?.request === request) ordersRequestRef.current = null;
      });
    ordersRequestRef.current = { owner: user, request };
    return request;
  }, [user]);

  const refreshData = useCallback(async (signal) => {
    setLoading(true);
    dispatch({ type: 'CATALOG_LOADING' });
    try {
      let products;
      try {
        products = await apiFetch('/api/productos', { signal });
      } catch (error) {
        if (!signal?.aborted && userRef.current === user) {
          dispatch({ type: 'CATALOG_ERROR', payload: 'No pudimos cargar el menú. Intentá nuevamente.' });
        }
        throw error;
      }
      if (signal?.aborted || userRef.current !== user) return;
      dispatch({ type: 'SYNC_CATALOG', payload: products.map(mapProduct) });
      if (user) {
        await refreshOrders(signal);
      }
      if (user?.role === 'admin' && userRef.current === user && !signal?.aborted) {
        const inventory = await apiFetch('/api/stock/ingredientes?activo=true', { signal });
        if (userRef.current === user && !signal?.aborted) {
          dispatch({ type: 'SYNC_INVENTORY', payload: inventory.map(mapInventory) });
        }
      }
    } finally {
      if (userRef.current === user && !signal?.aborted) setLoading(false);
    }
  }, [user, refreshOrders]);

  useEffect(() => {
    const controller = new AbortController();
    // El cleanup de StrictMode puede cancelar la carga antes de iniciar la consulta.
    Promise.resolve().then(() => {
      if (!controller.signal.aborted) return refreshData(controller.signal);
      return undefined;
    }).catch(() => undefined);
    return () => {
      controller.abort();
      dispatch({ type: 'RESET_PRIVATE_DATA' });
    };
  }, [refreshData]);

  useEffect(() => {
    if (!['EMPLEADO', 'ADMINISTRADOR', 'DUENIO'].includes(user?.backendRole)) return undefined;
    let controller = null;
    const updateOrders = async () => {
      if (document.hidden || controller) return;
      controller = new AbortController();
      try {
        await refreshOrders(controller.signal);
      } catch {
        // Conserva el último tablero disponible; reintenta en el siguiente ciclo.
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

  const createProduct = async (payload) => {
    const created = await apiFetch('/api/productos', {
      method: 'POST',
      body: JSON.stringify({
        categoria_id: payload.categoryId,
        nombre: payload.name,
        descripcion: payload.description,
        precio_base: payload.price,
        imagen_url: payload.image,
        ingredientes: [{
          ingrediente_id: Number(payload.ingredientId),
          cantidad_requerida: Number(payload.ingredientQuantity),
          es_base: true,
        }],
      }),
    });
    const product = mapProduct(created);
    dispatch({ type: 'ADD_CATALOG_ITEM', payload: product });
    return product;
  };

  const deactivateProduct = async (id) => {
    await apiFetch(`/api/productos/${id}/estado`, {
      method: 'PATCH',
      body: JSON.stringify({ activo: false }),
    });
    dispatch({ type: 'DELETE_CATALOG_ITEM', payload: id });
  };

  const changeOrderStatus = async (id, status) => {
    const updated = await apiFetch(`/api/pedidos/${id}/estado`, {
      method: 'PATCH',
      body: JSON.stringify({ estado: status.toUpperCase() }),
    });
    const order = mapOrder(updated);
    dispatch({ type: 'UPDATE_ORDER_STATUS', payload: { id, status: order.status } });
    return order;
  };

  const placeOrder = async ({ address, zone, items }) => {
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

  const startDigitalPayment = async (order) => apiFetch('/api/pagos/billetera/iniciar', {
    method: 'POST',
    body: JSON.stringify({ pedido_id: order.id, metodo_pago: 'MERCADO_PAGO' }),
  });

  const createIngredient = async (payload) => {
    const created = await apiFetch('/api/stock/ingredientes', {
      method: 'POST',
      body: JSON.stringify({
        nombre: payload.name,
        unidad_medida: payload.unit,
        cantidad_actual: Number(payload.stock),
        umbral_minimo: Number(payload.min),
      }),
    });
    const item = mapInventory(created);
    dispatch({ type: 'ADD_INVENTORY_ITEM', payload: item });
    return item;
  };

  const replenishIngredient = async (id, quantity = 1) => {
    // Actualizacion optimista: Render y Supabase estan en regiones distintas,
    // pero el operador debe ver el cambio apenas toca el boton.
    dispatch({ type: 'UPDATE_INVENTORY_STOCK', payload: { id, delta: quantity } });
    try {
      await apiFetch(`/api/stock/ingredientes/${id}/reposiciones`, {
        method: 'POST',
        body: JSON.stringify({ cantidad: quantity, origen: 'PANEL_WEB' }),
      });
    } catch (error) {
      dispatch({ type: 'UPDATE_INVENTORY_STOCK', payload: { id, delta: -quantity } });
      throw error;
    }
  };

  return (
    <DataContext.Provider value={{
      state: { ...state, orders: user && state.ordersOwner === user ? state.orders : [] },
      dispatch,
      loading,
      refreshData,
      createProduct,
      deactivateProduct,
      changeOrderStatus,
      placeOrder,
      startDigitalPayment,
      createIngredient,
      replenishIngredient,
    }}>
      {children}
    </DataContext.Provider>
  );
}

export const useData = () => useContext(DataContext);
