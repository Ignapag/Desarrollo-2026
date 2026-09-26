const fs = require("fs");
const path = require("path");

const file = path.join(__dirname, "src", "components", "client", "CartDrawer.jsx");
let content = fs.readFileSync(file, "utf-8");

const oldFunc = `  const placeOrder = () => {
    if (cart.length === 0) return;
    dispatch({ 
      type: 'PLACE_ORDER', 
      payload: { 
        client: 'Cliente Monu', 
        address: 'Calle 50 #782', 
        total, 
        items: cart.map(i => \`\${i.quantity}x \${i.name}\`) 
      } 
    });
    setIsSuccess(true);
    setTimeout(() => {
      setIsSuccess(false);
      onClose();
    }, 3000);
  };`;

const newFunc = `  const placeOrder = () => {
    if (cart.length === 0) return;
    setIsPayingMP(true);
    
    setTimeout(() => {
      setIsPayingMP(false);
      dispatch({ 
        type: 'PLACE_ORDER', 
        payload: { 
          client: 'Cliente Monu', 
          address: 'Calle 50 #782', 
          total, 
          items: cart.map(i => \`\${i.quantity}x \${i.name}\`) 
        } 
      });
      setIsSuccess(true);
      setTimeout(() => {
        setIsSuccess(false);
        onClose();
      }, 3000);
    }, 2500);
  };`;

content = content.replace(oldFunc, newFunc);
fs.writeFileSync(file, content, "utf-8");