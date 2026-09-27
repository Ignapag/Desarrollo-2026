const fs = require('fs');
const path = require('path');

// 1. Update DataContext.jsx to add phone numbers to mock orders
const dataPath = path.join(__dirname, 'src', 'shared', 'store', 'DataContext.jsx');
let dataContent = fs.readFileSync(dataPath, 'utf-8');
dataContent = dataContent.replace(/address: 'Calle 48 #620, La Plata',/g, "address: 'Calle 48 #620, La Plata', phone: '5492215550102',");
dataContent = dataContent.replace(/address: 'El Dique',/g, "address: 'El Dique, Ensenada', phone: '5492215550148',");
dataContent = dataContent.replace(/address: 'Punta Lara',/g, "address: 'Punta Lara, Ensenada', phone: '5492215550199',");
fs.writeFileSync(dataPath, dataContent, 'utf-8');

// 2. Update DeliveryPanel.jsx to add Maps and WhatsApp buttons
const deliveryPath = path.join(__dirname, 'src', 'fulfillment', 'DeliveryPanel.jsx');
if (fs.existsSync(deliveryPath)) {
  let delContent = fs.readFileSync(deliveryPath, 'utf-8');
  
  // Find where the address is rendered and inject buttons below it
  const addressBlock = `<div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-monu-green shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-bold text-gray-500">Dirección de entrega</p>
                    <p className="font-extrabold text-monu-dark">{order.address}</p>
                  </div>
                </div>`;
  
  const newAddressBlock = `<div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-monu-green shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-bold text-gray-500">Dirección de entrega</p>
                    <p className="font-extrabold text-monu-dark">{order.address}</p>
                  </div>
                </div>
                
                {/* Botones de acción rápida para el repartidor */}
                <div className="flex gap-2 mt-4 border-t border-gray-100 pt-4">
                  <a 
                    href={\`https://maps.google.com/?q=\${encodeURIComponent(order.address + ', La Plata, Buenos Aires')}\`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex-1 bg-blue-50 hover:bg-blue-100 text-blue-600 font-bold py-2 px-3 rounded-xl flex items-center justify-center gap-2 transition-colors text-sm"
                  >
                    🗺️ Ver Ruta
                  </a>
                  {order.phone && (
                    <a 
                      href={\`https://wa.me/\${order.phone.replace(/\\D/g, '')}\`}
                      target="_blank"
                      rel="noreferrer"
                      className="flex-1 bg-green-50 hover:bg-green-100 text-green-600 font-bold py-2 px-3 rounded-xl flex items-center justify-center gap-2 transition-colors text-sm"
                    >
                      💬 WhatsApp
                    </a>
                  )}
                </div>`;
  
  delContent = delContent.replace(addressBlock, newAddressBlock);
  fs.writeFileSync(deliveryPath, delContent, 'utf-8');
}

console.log("Delivery and DataContext updated.");