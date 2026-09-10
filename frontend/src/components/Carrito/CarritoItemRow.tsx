// src/components/Carrito/CarritoItemRow.tsx
import type { CarritoItem } from "../../types/cart";
import { useCarrito } from "../../context/CarritoContext";

interface CarritoItemRowProps {
    item: CarritoItem;
}

function resumenPersonalizacion(item: CarritoItem): string | null {
    const { producto, personalizacion } = item;

    const quitados = personalizacion.baseQuitados
    .map((id) => producto.ingredientesBase.find((i) => i.id === id)?.nombre)
    .filter(Boolean);

    const agregados = personalizacion.opcionalesAgregados
    .map((a) => producto.ingredientesOpcionales.find((i) => i.id === a.ingredienteId)?.nombre)
    .filter(Boolean);

    const partes: string[] = [];
    if (quitados.length > 0) partes.push(`Sin ${quitados.join(", ")}`);
    if (agregados.length > 0) partes.push(`+ ${agregados.join(", ")}`);

    return partes.length > 0 ? partes.join(" · ") : null;
}

export function CarritoItemRow({ item }: CarritoItemRowProps) {
    const { actualizarCantidad, quitarItem } = useCarrito();
    const resumen = resumenPersonalizacion(item);
    const subtotal = item.precioUnitario * item.cantidad;

    return (
    <li className="flex gap-3 pb-4 border-b border-stone-100 last:border-b-0 last:pb-0">
        <img
        src={item.producto.imagenRepresentativa}
        alt={item.producto.nombre}
        className="w-16 h-16 object-cover rounded-xl shrink-0"
        />

        <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
            <h3 className="font-jakarta font-semibold text-sm text-stone-900 truncate">
            {item.producto.nombre}
            </h3>
            <button
            type="button"
            onClick={() => quitarItem(item.id)}
            className="text-stone-300 hover:text-stone-500 transition-colors shrink-0"
            aria-label="Quitar del carrito"
            >
            <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            </button>
        </div>

        {resumen && (
            <p className="font-inter text-xs text-stone-400 mt-0.5">{resumen}</p>
        )}

        <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-2 bg-stone-50 rounded-full px-1 py-1">
            <button
                type="button"
                onClick={() => actualizarCantidad(item.id, item.cantidad - 1)}
                className="w-6 h-6 flex items-center justify-center rounded-full bg-white shadow-sm text-stone-600 font-bold"
                aria-label="Restar cantidad"
            >
                −
            </button>
            <span className="font-inter text-sm text-stone-700 w-4 text-center">
                {item.cantidad}
            </span>
            <button
                type="button"
                onClick={() => actualizarCantidad(item.id, item.cantidad + 1)}
                className="w-6 h-6 flex items-center justify-center rounded-full bg-white shadow-sm text-stone-600 font-bold"
                aria-label="Sumar cantidad"
            >
                +
            </button>
            </div>

            <span className="font-jakarta font-semibold text-sm text-stone-900">
            ${subtotal.toLocaleString("es-AR")}
            </span>
        </div>
        </div>
    </li>
    );
}