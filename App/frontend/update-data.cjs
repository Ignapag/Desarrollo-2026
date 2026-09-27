const fs = require('fs');
const path = require('path');

const ctxPath = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let content = fs.readFileSync(ctxPath, 'utf-8');

// Update getInitialState
content = content.replace(
  `const savedOrders = localStorage.getItem('monu_orders');
      if (savedOrders) {
        return { ...initialState, orders: JSON.parse(savedOrders) };
      }`,
  `const savedOrders = localStorage.getItem('monu_orders');
      const savedCatalog = localStorage.getItem('monu_catalog');
      let st = { ...initialState };
      if (savedOrders) st.orders = JSON.parse(savedOrders);
      if (savedCatalog) st.catalog = JSON.parse(savedCatalog);
      return st;`
);

// Update listener
content = content.replace(
  `if (e.key === 'monu_orders') {
        dispatch({ type: 'SYNC_ORDERS', payload: JSON.parse(e.newValue || '[]') });
      }`,
  `if (e.key === 'monu_orders') {
        dispatch({ type: 'SYNC_ORDERS', payload: JSON.parse(e.newValue || '[]') });
      }
      if (e.key === 'monu_catalog') {
        dispatch({ type: 'SYNC_CATALOG', payload: JSON.parse(e.newValue || '[]') });
      }`
);

// Update saver
content = content.replace(
  `useEffect(() => {
    localStorage.setItem('monu_orders', JSON.stringify(state.orders));
  }, [state.orders]);`,
  `useEffect(() => {
    localStorage.setItem('monu_orders', JSON.stringify(state.orders));
  }, [state.orders]);

  useEffect(() => {
    localStorage.setItem('monu_catalog', JSON.stringify(state.catalog));
  }, [state.catalog]);`
);

// Update reducer
content = content.replace(
  `case 'SYNC_ORDERS':
      return { ...state, orders: action.payload };`,
  `case 'SYNC_ORDERS':
      return { ...state, orders: action.payload };
    case 'SYNC_CATALOG':
      return { ...state, catalog: action.payload };`
);

fs.writeFileSync(ctxPath, content, 'utf-8');
console.log("DataContext Catalog Sync updated.");