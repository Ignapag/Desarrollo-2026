// src/components/Carrito/CarritoIcono.tsx
import { useCarrito } from "../../context/CarritoContext";

interface CarritoIconoProps {
    onClick: () => void;
}

export function CarritoIcono({ onClick }: CarritoIconoProps) {
    const { cantidadTotal } = useCarrito();

    return (
    <button
        type="button"
        onClick={onClick}
        className="relative w-11 h-11 flex items-center justify-center rounded-full bg-white shadow-sm hover:shadow-md transition-shadow border border-stone-100"
        aria-label="Ver carrito"
    >
        <svg className="w-5 h-5 text-stone-700" viewBox="0 0 24 24" fill="none">
        <path
            d="M3 3h2l.4 2M7 13h10l3-8H5.4M7 13L5.4 5M7 13l-1.5 6h11.5M9 20a1 1 0 100-2 1 1 0 000 2zm8 0a1 1 0 100-2 1 1 0 000 2z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
        </svg>
        {cantidadTotal > 0 && (
        <span className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center rounded-full bg-naranja text-white text-[11px] font-jakarta font-bold">
            {cantidadTotal}
        </span>
        )}
    </button>
    );
}