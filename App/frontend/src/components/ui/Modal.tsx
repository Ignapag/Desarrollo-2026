import { useEffect } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
    abierto: boolean;
    onCerrar: () => void;
    titulo: string;
    children: React.ReactNode;
    footer?: React.ReactNode;
}

export function Modal({ abierto, onCerrar, titulo, children, footer }: ModalProps) {
  // Bloquea el scroll del body mientras el modal está abierto
    useEffect(() => {
    if (abierto) {
        document.body.style.overflow = "hidden";
    } else {
        document.body.style.overflow = "";
    }
    return () => {
        document.body.style.overflow = "";
    };
    }, [abierto]);

  // Cierra con Escape
    useEffect(() => {
    if (!abierto) return;
    const handleKey = (e: KeyboardEvent) => {
        if (e.key === "Escape") onCerrar();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
    }, [abierto, onCerrar]);

    if (!abierto) return null;

    return createPortal(
    <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-titulo"
        className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
    >
      {/* Overlay */}
        <div
        className="absolute inset-0 bg-carbon/60 backdrop-blur-sm"
        onClick={onCerrar}
        />

      {/* Panel */}
        <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-xl flex flex-col max-h-[90dvh]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0">
            <h2
            id="modal-titulo"
            className="font-jakarta font-bold text-lg text-stone-900 leading-tight"
            >
            {titulo}
            </h2>
            <button
            type="button"
            onClick={onCerrar}
            className="w-8 h-8 flex items-center justify-center rounded-full bg-stone-100 hover:bg-stone-200 transition-colors"
            aria-label="Cerrar"
            >
            <svg className="w-4 h-4 text-stone-500" viewBox="0 0 16 16" fill="none">
                <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                />
            </svg>
            </button>
        </div>

        {/* Body scrolleable */}
        <div className="overflow-y-auto px-5 pb-4 flex-1">
            {children}
        </div>

        {/* Footer fijo */}
        {footer && (
            <div className="px-5 py-4 border-t border-stone-100 shrink-0">
            {footer}
            </div>
        )}
        </div>
    </div>,
    document.body
    );
}