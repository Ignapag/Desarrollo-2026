import { useState } from "react";
import type { Producto, PersonalizacionPayload } from "../../types/product";
import { Modal } from "../ui/Modal";
import { PersonalizacionSelector } from "./PersonalizacionSelector";

interface ProductoModalProps {
    producto: Producto;
    abierto: boolean;
    onCerrar: () => void;
    onConfirmar: (payload: PersonalizacionPayload, precioTotal: number) => void;
}

export function ProductoModal({ producto, abierto, onCerrar, onConfirmar }: ProductoModalProps) {
    const [payloadActual, setPayloadActual] = useState<PersonalizacionPayload>({
    baseQuitados: [],
    opcionalesAgregados: [],
    });
    const [costoExtra, setCostoExtra] = useState(0);

    const precioTotal = producto.precioBase + costoExtra;

    const footerContenido = (
    <div className="flex flex-col gap-3 w-full">
        <div className="flex justify-between items-center">
        <span className="font-inter text-stone-500 text-sm">Precio final</span>
        <span className="font-jakarta font-bold text-xl text-stone-900">
            ${precioTotal.toLocaleString("es-AR")}
        </span>
        </div>
        <button
        type="button"
        onClick={() => onConfirmar(payloadActual, precioTotal)}
        className="w-full bg-naranja hover:bg-naranja/90 text-white font-inter font-semibold py-3.5 rounded-2xl transition-colors shadow-sm"
        >
        Agregar al pedido
        </button>
    </div>
    );

    return (
    <Modal
        abierto={abierto}
        onCerrar={onCerrar}
        titulo={producto.nombre}
        footer={footerContenido}
    >
        <div className="flex flex-col gap-4">
        <img
            src={producto.imagenRepresentativa}
            alt={producto.nombre}
            className="w-full h-44 object-cover rounded-2xl"
        />
        <p className="font-inter text-sm text-stone-600">{producto.descripcion}</p>

        <PersonalizacionSelector
            producto={producto}
            onChange={(payload, extra) => {
            setPayloadActual(payload);
            setCostoExtra(extra);
            }}
        />
        </div>
    </Modal>
    );
}