// src/components/Menu/PersonalizacionSelector.tsx
import { useEffect } from "react";
import { usePersonalizacion } from "../../hooks/usePersonalizacion";
import type { Producto, PersonalizacionPayload } from "../../types/product";

interface PersonalizacionSelectorProps {
  producto: Producto;
  onChange: (payload: PersonalizacionPayload, costoExtra: number) => void;
}

export function PersonalizacionSelector({
  producto,
  onChange,
}: PersonalizacionSelectorProps) {
  const {
    baseEstados,
    opcionalesEstados,
    toggleBase,
    toggleOpcional,
    costoExtra,
    payload,
  } = usePersonalizacion(
    producto.ingredientesBase,
    producto.ingredientesOpcionales
  );

  useEffect(() => {
    onChange(payload, costoExtra);
  }, [payload, costoExtra, onChange]);

  const hayBase = baseEstados.length > 0;
  const hayOpcionales = opcionalesEstados.length > 0;

  if (!hayBase && !hayOpcionales) {
    return (
      <p className="font-inter text-sm text-stone-400 mt-2">
        Este producto no tiene personalizaciones disponibles.
      </p>
    );
  }

  return (
    <div className="mt-4 flex flex-col gap-6">

      {/* ── Ingredientes base ── */}
      {hayBase && (
        <section>
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="font-jakarta font-semibold text-base text-stone-800">
              Ingredientes
            </h3>
            <span className="font-inter text-xs text-stone-400">
              Destildá lo que no querés
            </span>
          </div>

          <ul className="flex flex-col gap-2">
            {baseEstados.map(({ ingrediente, incluido }) => (
              <li key={ingrediente.id}>
                <button
                  type="button"
                  onClick={() => toggleBase(ingrediente.id)}
                  className={`
                    w-full flex items-center justify-between
                    px-4 py-3 rounded-2xl border transition-colors duration-150
                    ${
                      incluido
                        ? "bg-white border-stone-200 hover:border-stone-300"
                        : "bg-stone-50 border-stone-200"
                    }
                  `}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`
                        w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0
                        transition-colors duration-150
                        ${incluido ? "border-stone-400 bg-stone-400" : "border-stone-300"}
                      `}
                    >
                      {incluido && (
                        <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                          <path
                            d="M2 6l3 3 5-5"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>

                    <span
                      className={`font-inter text-sm transition-colors duration-150 ${
                        incluido ? "text-stone-700" : "text-stone-400 line-through"
                      }`}
                    >
                      {ingrediente.nombre}
                    </span>
                  </div>

                  <span className="font-inter text-xs text-stone-400">
                    {incluido ? "Incluido" : "Quitado"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Ingredientes opcionales ── */}
      {hayOpcionales && (
        <section>
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="font-jakarta font-semibold text-base text-stone-800">
              Agregados
            </h3>
            <span className="font-inter text-xs text-stone-400">
              Tildá lo que querés sumar
            </span>
          </div>

          <ul className="flex flex-col gap-2">
            {opcionalesEstados.map(({ ingrediente, seleccionado }) => (
              <li key={ingrediente.id}>
                <button
                  type="button"
                  onClick={() => toggleOpcional(ingrediente.id)}
                  className={`
                    w-full flex items-center justify-between
                    px-4 py-3 rounded-2xl border transition-colors duration-150
                    ${
                      seleccionado
                        ? "bg-naranja/10 border-naranja"
                        : "bg-white border-stone-200 hover:border-stone-300"
                    }
                  `}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`
                        w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0
                        transition-colors duration-150
                        ${seleccionado ? "border-naranja bg-naranja" : "border-stone-300"}
                      `}
                    >
                      {seleccionado && (
                        <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                          <path
                            d="M2 6l3 3 5-5"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>

                    <span className="font-inter text-sm text-stone-700">
                      {ingrediente.nombre}
                    </span>
                  </div>

                  <span
                    className={`font-inter text-sm font-medium ${
                      ingrediente.costoAdicional > 0 ? "text-naranja" : "text-stone-400"
                    }`}
                  >
                    {ingrediente.costoAdicional > 0
                      ? `+ $${ingrediente.costoAdicional.toLocaleString("es-AR")}`
                      : "Sin costo"}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {/* Resumen costo extra */}
          {costoExtra > 0 && (
            <div className="mt-4 flex justify-between items-center px-1">
              <span className="font-inter text-sm text-stone-500">
                Extras seleccionados
              </span>
              <span className="font-jakarta font-semibold text-sm text-naranja">
                + ${costoExtra.toLocaleString("es-AR")}
              </span>
            </div>
          )}
        </section>
      )}

    </div>
  );
}
