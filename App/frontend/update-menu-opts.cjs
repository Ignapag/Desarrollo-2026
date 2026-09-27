const fs = require('fs');
const path = require('path');

const menuPath = path.join(__dirname, 'src', 'ordering', 'Menu.jsx');
let menu = fs.readFileSync(menuPath, 'utf-8');

// I need to update the options UI.
// The current options UI looks like this:
const oldOptions = `<div className="mt-3 animate-in slide-in-from-top-2">
              <input 
                type="text" 
                placeholder="Ej: Sin cebolla, extra cheddar..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-yellow-50 border border-yellow-200 rounded-xl px-3 py-2 text-sm text-monu-dark placeholder:text-yellow-600/50 focus:outline-none focus:border-yellow-400"
              />
            </div>`;

const newOptions = `<div className="mt-3 animate-in slide-in-from-top-2 bg-yellow-50 border border-yellow-200 rounded-xl p-3">
              <p className="text-xs font-bold text-yellow-800 mb-2">Sacar ingredientes:</p>
              <div className="flex flex-wrap gap-2 mb-3">
                {['Sin Cebolla', 'Sin Tomate', 'Sin Lechuga', 'Sin Pepinillos', 'Sin Bacon', 'Sin Cheddar'].map(ing => (
                  <label key={ing} className="flex items-center gap-1.5 text-xs font-bold text-yellow-900 bg-yellow-100/50 px-2 py-1 rounded-md cursor-pointer hover:bg-yellow-200 transition">
                    <input 
                      type="checkbox" 
                      className="accent-monu-orange"
                      checked={notes.includes(ing)}
                      onChange={(e) => {
                        if(e.target.checked) {
                          setNotes(notes ? notes + ', ' + ing : ing);
                        } else {
                          setNotes(notes.replace(ing + ', ', '').replace(', ' + ing, '').replace(ing, ''));
                        }
                      }}
                    />
                    {ing}
                  </label>
                ))}
              </div>
              <input 
                type="text" 
                placeholder="Otras notas / extras..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full bg-white border border-yellow-300 rounded-lg px-3 py-2 text-sm text-monu-dark placeholder:text-gray-400 focus:outline-none focus:border-monu-orange"
              />
            </div>`;

menu = menu.replace(oldOptions, newOptions);

fs.writeFileSync(menuPath, menu, 'utf-8');
console.log("Menu Customizations updated");