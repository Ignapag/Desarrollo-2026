import { createContext, useContext, useReducer, useEffect } from 'react';

// ==========================================
// TODO BACKEND (Ignacio / José): 
// Este `initialState` es 100% de prueba para que Emilio diseñe las pantallas.
// En producción, estos arreglos deben arrancar vacíos ([]) y llenarse 
// haciendo `fetch()` a su API usando un `useEffect` en el DataProvider.
// ==========================================
const initialState = {
  cart: [],
  orders: [
    { id: 1042, client: 'Martina Gómez', address: 'Calle 48 #620, La Plata', status: 'en_camino', total: 19900, items: ['2x Doble Cheddar', '1x Papas Monu'], date: new Date().toISOString() },
    { id: 1041, client: 'Lucas Fernández', address: 'El Dique', status: 'en_preparacion', total: 13300, items: ['1x Monu Bacon', '2x Gaseosa 500ml'], date: new Date().toISOString() },
    { id: 1040, client: 'Sofía Ramírez', address: 'Punta Lara', status: 'listo', total: 24300, items: ['2x Monu Clásica', '1x Papas con Cheddar'], date: new Date().toISOString() },
    { id: 1039, client: 'Diego Pereyra', address: 'El Dique', status: 'entregado', total: 11200, items: ['1x Smash Burger'], date: new Date().toISOString() },
    { id: 1043, client: 'Camila Suárez', address: 'Punta Lara', status: 'pendiente', total: 15500, items: ['1x Veggie Deluxe', '1x Agua'], date: new Date().toISOString() },
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

function dataReducer(state, action) {
  switch (action.type) {
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
    
    // ==========================================
    // TODO BACKEND:
    // Estas acciones (UPDATE_ORDER_STATUS y PLACE_ORDER) actualmente actualizan el estado local de React.
    // Antes de despachar esto al `dataReducer`, el front debería hacer un `fetch('/api/orders', { method: 'POST' })`
    // y solo actualizar este estado si el backend respondió OK.
    // ==========================================
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
        orders: [{ id: 1044 + state.orders.length, ...action.payload, status: 'pendiente', date: new Date().toISOString() }, ...state.orders],
        cart: []
      }
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

  // Ejemplo para el backend de cómo se deberían cargar los datos al inicio
  // useEffect(() => {
  //   fetch('/api/orders').then(res => res.json()).then(data => dispatch({ type: 'SET_ORDERS', payload: data }))
  // }, []);

  return (
    <DataContext.Provider value={{ state, dispatch }}>
      {children}
    </DataContext.Provider>
  );
}

export const useData = () => useContext(DataContext);