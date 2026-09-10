import { useState } from "react";
import { ProductoCard } from "./components/Menu/ProductoCard";
import { CarritoIcono } from "./components/Carrito/CarritoIcono";
import { CarritoDrawer } from "./components/Carrito/CarritoDrawer";
import type { Producto } from "./types/product";

const productoDePrueba: Producto = {
  id: "1",
  nombre: "Burger Clásica",
  descripcion: "Carne, cheddar, lechuga, tomate y salsa especial.",
  precioBase: 8500,
  imagenRepresentativa: "https://placehold.co/400x300",
  categoria: "Hamburguesas",
  ordenVisualizacion: 1,
  activo: true,
  ingredientesBase: [
    { id: "b1", nombre: "Lechuga", enStock: true },
    { id: "b2", nombre: "Tomate", enStock: true },
  ],
  ingredientesOpcionales: [
  { id: "o1", nombre: "Bacon", costoAdicional: 900, activo: true },
  { id: "o2", nombre: "Cheddar extra", costoAdicional: 500, activo: true },
],
};

function App() {
  const [carritoAbierto, setCarritoAbierto] = useState(false);

  return (
    <div className="min-h-screen bg-crema">
      <header className="flex items-center justify-between px-4 py-4 max-w-3xl mx-auto">
        <h1 className="font-jakarta font-extrabold text-lg text-verde-monu">Monu Burger</h1>
        <CarritoIcono onClick={() => setCarritoAbierto(true)} />
      </header>

      <div className="max-w-sm mx-auto mt-6">
        <ProductoCard producto={productoDePrueba} />
      </div>

      <CarritoDrawer abierto={carritoAbierto} onCerrar={() => setCarritoAbierto(false)} />
    </div>
  );
}

export default App;