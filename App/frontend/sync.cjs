const fs = require('fs');
const path = require('path');

const ctxPath = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(ctxPath, 'utf-8');

// Inject the custom hook logic for DataProvider to sync orders via localStorage
const providerOld = `export function DataProvider({ children }) {
  const [state, dispatch] = useReducer(dataReducer, initialState);`;

const providerNew = `export function DataProvider({ children }) {
  // Sync orders with localStorage
  const getInitialState = () => {
    try {
      const savedOrders = localStorage.getItem('monu_orders');
      if (savedOrders) {
        return { ...initialState, orders: JSON.parse(savedOrders) };
      }
    } catch(e) {}
    return initialState;
  };

  const [state, dispatch] = useReducer(dataReducer, getInitialState());

  // Listen to cross-tab updates
  useEffect(() => {
    const handleStorage = (e) => {
      if (e.key === 'monu_orders') {
        dispatch({ type: 'SYNC_ORDERS', payload: JSON.parse(e.newValue || '[]') });
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  // Save to localStorage when orders change
  useEffect(() => {
    localStorage.setItem('monu_orders', JSON.stringify(state.orders));
  }, [state.orders]);`;

content = content.replace(providerOld, providerNew);

// Add SYNC_ORDERS to reducer
const reducerOld = `function dataReducer(state, action) {
  switch (action.type) {`;

const reducerNew = `function dataReducer(state, action) {
  switch (action.type) {
    case 'SYNC_ORDERS':
      return { ...state, orders: action.payload };`;

content = content.replace(reducerOld, reducerNew);

// Need to make sure useEffect is imported
content = content.replace("import { createContext, useContext, useReducer } from 'react';", "import { createContext, useContext, useReducer, useEffect } from 'react';");

fs.writeFileSync(ctxPath, content, 'utf-8');
console.log("DataContext syncing applied!");