// src/components/Carrito/CarritoDrawer.tsx
import { createPortal } from "react-dom";
import { useCarrito } from "../../context/CarritoContext";
import { CarritoItemRow } from "./CarritoItemRow";

interface CarritoDrawerProps {
    abierto: boolean;
    onCerrar: () => void;
}

export function CarritoDrawer({ abierto, onCerrar }: CarritoDrawerProps) {
    const { items, total, vaciarCarrito } = useCarrito();

    if (!abierto) return null;

    return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
        <div
        className="absolute inset-0 bg-carbon/60 backdrop-blur-sm"
        onClick={onCerrar}
        />

        <div className="relative w-full sm:max-w-md bg-white h-full shadow-xl flex flex-col">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0 border-b border-stone-100">
            <h2 className="font-jakarta font-bold text-lg text-stone-900">Tu pedido</h2>
            <button
            type="button"
            onClick={onCerrar}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-stone-100 hover:bg-stone-200 transition-colors"
            aria-label="Cerrar carrito"
            >
            <svg className="w-4 h-4 text-stone-500" viewBox="0 0 16 16" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            </button>
        </div>

        <div className="overflow-y-auto flex-1 px-5 py-4">
            {items.length === 0 ? (
            <p className="font-inter text-sm text-stone-400 text-center mt-10">
                Todavía no agregaste nada a tu pedido.
            </p>
            ) : (
            <ul className="flex flex-col gap-4">
                {items.map((item) => (
                <CarritoItemRow key={item.id} item={item} />
                ))}
            </ul>
            )}
        </div>

        {items.length > 0 && (
            <div className="px-5 py-4 border-t border-stone-100 shrink-0 flex flex-col gap-3">
            <div className="flex justify-between items-center">
                <span className="font-inter text-stone-500 text-sm">Total</span>
                <span className="font-jakarta font-bold text-xl text-stone-900">
                ${total.toLocaleString("es-AR")}
                </span>
            </div>
            <button
                type="button"
                disabled
                className="w-full bg-naranja/40 text-white font-inter font-semibold py-3.5 rounded-2xl cursor-not-allowed"
                title="Se habilita en la etapa de Integración con el módulo de pedidos"
            >
                Continuar pedido
            </button>
            <button
                type="button"
                onClick={vaciarCarrito}
                className="w-full text-stone-400 hover:text-stone-600 font-inter text-sm transition-colors"
            >
                Vaciar carrito
            </button>
            </div>
        )}
        </div>
    </div>,
    document.body
    );
}   