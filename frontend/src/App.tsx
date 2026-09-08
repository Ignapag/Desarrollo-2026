import { ProductoCard } from "./components/Menu/ProductoCard";
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
  return (
    <div className="max-w-sm mx-auto mt-10">
      <ProductoCard producto={productoDePrueba} />
    </div>
  );
}

export default App;
