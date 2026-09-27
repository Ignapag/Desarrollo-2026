import { createContext, useContext, useReducer, useEffect } from 'react';

import { useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { apiFetch } from '../api/http';

// ==========================================
// Datos de demostracion mientras la API carga o si el backend esta fuera de linea.
// Una respuesta exitosa reemplaza catalogo, pedidos e inventario.
// ==========================================
const initialState = {
  catalog: [
    { id: 1, name: 'Cheese', description: 'Ingredientes: Carne, cheddar, salsa monu.', variants: [{name: 'Simple', price: 11000}, {name: 'Doble', price: 13500}, {name: 'Triple', price: 15500}], category: 'Nuestras Burgers', image: '/menu/chesee burger.jpg' },
    { id: 2, name: 'Bacon', description: 'Ingredientes: Carne, cheddar, bacon, salsa monu.', variants: [{name: 'Simple', price: 12000}, {name: 'Doble', price: 14500}, {name: 'Triple', price: 16500}], category: 'Nuestras Burgers', image: '/menu/BaconBurger.jpg' },
    { id: 3, name: 'Crispy', description: 'Ingredientes: Carne, cheddar, bacon, cebolla crispy, alioli.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/CrispyBurger.jpg' },
    { id: 4, name: 'Monulibra', description: 'Ingredientes: Carne, cheddar, cebolla en cubos, ketchup, mostaza.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/MonuLibraBurgerjpg.jpg' },
    { id: 5, name: 'Monuburger', description: 'Ingredientes: Carne, cheddar, cebolla caramelizada, bacon, huevo, barbacoa.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: '/menu/MonuBurger.jpg' },
    { id: 6, name: 'La Típica', description: 'Ingredientes: Carne, cheddar, lechuga, tomate, mayonesa.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Nuestras Burgers', image: '/menu/LaTipicaBurger.jpg' },
    { id: 7, name: 'Witcher', description: 'Ingredientes: Carne, cheddar, bacon, tomate, lechuga, cebolla, pepinillos, mayonesa, ketchup.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/WitcherBurger.jpg' },
    { id: 8, name: '18 Supermash', description: 'Ingredientes: Carne smasheada, cheddar, panceta, pepinillo, salsa smash.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: '/menu/18supersmash.jpg' },
    { id: 9, name: 'Oklahoma', description: 'Ingredientes: Carne smasheada con cebolla cruda, cheddar, salsa monu.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/oklahomaBurger.jpg' },
    { id: 10, name: 'Provoteca', description: 'Ingredientes: Carne, provoleta, cebolla caramelizada, rúcula, alioli.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Nuestras Burgers', image: '/menu/ProvotecaBurger.jpg' },
    { id: 11, name: 'Big Monu', description: 'Ingredientes: Carne, cheddar, cebolla, lechuga, pepinillos, salsa monu.', variants: [{name: 'Simple', price: 13000}, {name: 'Doble', price: 15500}, {name: 'Triple', price: 17500}], category: 'Nuestras Burgers', image: '/menu/BigMonuBurger.jpg' },
    { id: 12, name: 'Not Monu', description: 'Ingredientes: Medallón NotCo, cheddar, mayonesa, tomate y lechuga.', variants: [{name: 'Simple', price: 13500}, {name: 'Doble', price: 16000}, {name: 'Triple', price: 18000}], category: 'Nuestras Burgers', image: '/menu/notMonu.jpg' },
    { id: 13, name: 'Nueva Jersey', description: 'Ingredientes: Carne, cheddar, bacon en cubos tiernizado y mayonesa ahumada.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Nuestras Burgers', image: null },
    { id: 14, name: 'Baconhoma', description: 'Ingredientes: Carne smasheada con cebolla cruda, cheddar, bacon, salsa monu.', variants: [{name: 'Simple', price: 14000}, {name: 'Doble', price: 16500}, {name: 'Triple', price: 18500}], category: 'Monufusión', image: null },
    { id: 15, name: 'Tipiteca', description: 'Ingredientes: Carne, provoleta, tomate, rúcula, mayonesa.', variants: [{name: 'Simple', price: 12500}, {name: 'Doble', price: 15000}, {name: 'Triple', price: 17000}], category: 'Monufusión', image: null },
    { id: 16, name: 'Keco', description: 'Ingredientes: Una carne smasheada, cheddar, cebolla crispy y alioli. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
    { id: 17, name: 'Cito', description: 'Ingredientes: Un medallón de carne, cheddar, cebolla en cubos, ketchup, mostaza, bacon. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
    { id: 18, name: 'Tino Andino', description: 'Ingredientes: Un medallón de carne, provoleta en medallón, cheddar en pan y mayonesa. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
    { id: 19, name: 'Santi', description: 'Ingredientes: Un medallón de carne, cheddar, cebolla crispy, lechuga y alioli. (NO INCLUYE PAPAS)', price: 9500, category: 'Opciones Individuales', image: null },
    { id: 20, name: 'Combo: Típica + Bacon', description: 'La Típica doble + Bacon simple + 1 Porción de Papas', price: 23000, category: 'Combos', image: null },
    { id: 21, name: 'Combo: Bacon + Típica', description: 'Bacon doble + La Típica simple + 1 Porción de Papas', price: 23000, category: 'Combos', image: null },
    { id: 22, name: 'Combo: Nuggets + Papas', description: 'Nuggets + Papas Fritas', price: 15000, category: 'Combos', image: '/menu/nuggetsmonu.jpg' },
    { id: 23, name: 'Papas Fritas (Porción)', description: 'Porción de papas fritas.', price: 8000, category: 'Acompañamientos', image: '/menu/papasfritasMonu.jpg' },
    { id: 24, name: 'Nuggets', description: '10 unidades. Incluye 2 dips (salsa monu y barbacoa)', price: 11000, category: 'Acompañamientos', image: '/menu/nuggetsmonu.jpg' },
    { id: 25, name: 'Coca Cola', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/cocacolamonu.jpg' },
    { id: 26, name: 'Sprite', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/sprite.jpg' },
    { id: 27, name: 'Fanta', description: '500ml', price: 2200, category: 'Bebidas', image: '/menu/fantamonu.jpg' },
    { id: 28, name: 'Salsa Monu', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
    { id: 29, name: 'Alioli', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
    { id: 30, name: 'Barbacoa', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
    { id: 31, name: 'Mayonesa', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
    { id: 32, name: 'Ketchup', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
    { id: 33, name: 'Mostaza', description: 'Dip extra', price: 1000, category: 'Dips Extra', image: null },
  ],
  cart: [],
  orders: [
    { id: 1042, client: 'Martina Gómez', address: 'Calle 48 #620, La Plata', phone: '5492215550102', status: 'en_camino', total: 19900, items: ['2x Doble Cheddar', '1x Papas Monu'], date: new Date().toISOString() },
    { id: 1041, client: 'Lucas Fernández', address: 'El Dique, Ensenada', phone: '5492215550148', status: 'en_preparacion', total: 13300, items: ['1x Monu Bacon', '2x Gaseosa 500ml'], date: new Date().toISOString() },
    { id: 1040, client: 'Sofía Ramírez', address: 'Punta Lara, Ensenada', phone: '5492215550199', status: 'listo', total: 24300, items: ['2x Monu Clásica', '1x Papas con Cheddar'], date: new Date().toISOString() },
    { id: 1039, client: 'Diego Pereyra', address: 'El Dique, Ensenada', phone: '5492215550148', status: 'entregado', total: 11200, items: ['1x Smash Burger'], date: new Date().toISOString() },
    { id: 1043, client: 'Camila Suárez', address: 'Punta Lara, Ensenada', phone: '5492215550199', status: 'pendiente', total: 15500, items: ['1x Veggie Deluxe', '1x Agua'], date: new Date().toISOString() },
  ],
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
    active: product.activo,
    available: product.disponible,
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
    items: order.items.map((item) => `${item.cantidad}x ${item.nombre_producto}`),
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
      return { ...state, orders: action.payload };
    case 'SYNC_CATALOG':
      return { ...state, catalog: action.payload };
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

  const refreshData = async () => {
    setLoading(true);
    try {
      const products = await apiFetch('/api/productos');
      dispatch({ type: 'SYNC_CATALOG', payload: products.map(mapProduct) });
      if (user) {
        const orders = await apiFetch('/api/pedidos');
        dispatch({ type: 'SYNC_ORDERS', payload: orders.map(mapOrder) });
      }
      if (user?.role === 'admin') {
        const inventory = await apiFetch('/api/stock/ingredientes?activo=true');
        dispatch({ type: 'SYNC_INVENTORY', payload: inventory.map(mapInventory) });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData().catch(() => undefined);
  }, [user?.id]);

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
          aclaraciones: item.notes || null,
        })),
      }),
    });
    const order = mapOrder(created);
    dispatch({ type: 'PLACE_ORDER', payload: order });
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
    await apiFetch(`/api/stock/ingredientes/${id}/reposiciones`, {
      method: 'POST',
      body: JSON.stringify({ cantidad: quantity, origen: 'PANEL_WEB' }),
    });
    dispatch({ type: 'UPDATE_INVENTORY_STOCK', payload: { id, delta: quantity } });
  };

  return (
    <DataContext.Provider value={{
      state,
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
