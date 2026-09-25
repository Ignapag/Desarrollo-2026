// src/components/Seguimiento/MisPedidosIcono.tsx
import { usePedidos } from "../../context/PedidosContext";

interface MisPedidosIconoProps {
    onClick: () => void;
}

export function MisPedidosIcono({ onClick }: MisPedidosIconoProps) {
    const { pedidos } = usePedidos();

    return (
    <button
        type="button"
        onClick={onClick}
        className="relative w-11 h-11 flex items-center justify-center rounded-full bg-white shadow-sm hover:shadow-md transition-shadow border border-stone-100"
        aria-label="Ver mis pedidos"
    >
        <svg className="w-5 h-5 text-stone-700" viewBox="0 0 24 24" fill="none">
        <path
            d="M4 4h16v4H4zM6 8v11a1 1 0 001 1h10a1 1 0 001-1V8M9 12h6"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
        </svg>
        {pedidos.length > 0 && (
        <span className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center rounded-full bg-verde-monu text-white text-[11px] font-jakarta font-bold">
            {pedidos.length}
        </span>
        )}
    </button>
    );
}