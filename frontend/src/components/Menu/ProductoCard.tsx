import { useState } from "react";
import type { Producto } from "../../types/product";
import { ProductoModal } from "./ProductoModal";

interface ProductoCardProps {
    producto: Producto;
}

export function ProductoCard({ producto }: ProductoCardProps) {
    const [modalAbierto, setModalAbierto] = useState(false);

    return (
    <>
        <div className="bg-white rounded-3xl p-4 shadow-sm hover:shadow-md transition-shadow border border-stone-100 flex flex-col h-full">
        <img
            src={producto.imagenRepresentativa}
            alt={producto.nombre}
            className="w-full h-40 object-cover rounded-2xl mb-4"
        />

        <div className="flex-grow flex flex-col">
            <h3 className="font-jakarta font-bold text-lg text-stone-900 mb-1">
            {producto.nombre}
            </h3>
            <p className="font-inter text-xs text-stone-500 line-clamp-2 mb-4 flex-grow">
            {producto.descripcion}
            </p>

            <div className="flex items-center justify-between mt-auto pt-2">
            <span className="font-jakarta font-bold text-lg text-stone-900">
                ${producto.precioBase.toLocaleString("es-AR")}
            </span>

            <button
                type="button"
                onClick={() => setModalAbierto(true)}
                className="bg-[#2E5C31] hover:bg-[#244A27] text-white font-inter font-medium text-sm px-4 py-2 rounded-xl transition-colors"
            >
                Agregar
            </button>
            </div>
        </div>
        </div>

        <ProductoModal
        producto={producto}
        abierto={modalAbierto}
        onCerrar={() => setModalAbierto(false)}
        onConfirmar={(payload, total) => {
            console.log("Ítem personalizado listo para el carrito:", { payload, total });
            setModalAbierto(false);
        }}
        />
    </>
    );
}