// Errores visibles para el usuario: mensajes genéricos, clase UserFacingError y
// traducción de respuestas HTTP de la API a textos en español seguros de mostrar.
export const DEFAULT_ERROR_MESSAGE = 'No pudimos completar la acción. Intentá nuevamente más tarde.';
export const CHECK_OPERATION_MESSAGE = 'No pudimos confirmar el resultado. Comprobá su estado antes de repetir la acción para evitar duplicaciones.';

// Sólo se construye con textos propios del frontend o traducciones exactas.
// Nunca pasar mensajes recibidos, excepciones, datos personales ni diagnósticos.
export class UserFacingError extends Error {
  constructor(message, { status, kind = 'validation', uncertain = false } = {}) {
    super(message);
    this.name = 'UserFacingError';
    this.status = status;
    this.kind = kind;
    this.uncertain = uncertain;
  }
}

// Texto a mostrar para cualquier error; los errores desconocidos usan `fallback`.
export function userErrorMessage(error, fallback = DEFAULT_ERROR_MESSAGE) {
  if (!(error instanceof UserFacingError)) {
    if (error?.status === 401) return 'La sesión venció. Volvé a ingresar.';
    if (error?.status === 403) return 'No tenés acceso a esta acción.';
    return fallback;
  }
  if (error.kind === 'request') return error.uncertain ? `${fallback} ${CHECK_OPERATION_MESSAGE}` : fallback;
  if (error.kind === 'connection') return `${fallback} Revisá tu conexión.${error.uncertain ? ` ${CHECK_OPERATION_MESSAGE}` : ' Intentá nuevamente.'}`;
  if (error.kind === 'timeout') return `${fallback} La espera terminó.${error.uncertain ? ` ${CHECK_OPERATION_MESSAGE}` : ' Intentá nuevamente.'}`;
  return error.message;
}

// Lista cerrada: no usar coincidencias parciales ni interpolar el texto recibido.
const businessMessages = new Map([
  ['Ese nombre de usuario ya existe', 'Ese nombre de usuario ya existe. Elegí otro.'],
  ['Stock insuficiente para el pedido', 'No hay insumos suficientes para preparar el pedido. Revisá los productos.'],
  ['Stock insuficiente para modificar el pedido', 'No hay insumos suficientes para modificar el pedido. Revisá los productos.'],
  ['Stock insuficiente para aumentar la cantidad', 'No hay insumos suficientes para aumentar la cantidad.'],
  ['No hay stock suficiente para la cantidad pedida. Revisá el carrito.', 'No hay stock suficiente para la cantidad pedida. Reducí las unidades del carrito e intentá nuevamente.'],
  ['La direccion no tiene cobertura activa', 'La dirección está fuera de la zona de entrega. Elegí otra dirección o retiro en el local.'],
  ['La cantidad acumulada del producto no puede superar 50', 'Podés pedir hasta 50 unidades de cada producto.'],
  ['El monto debe ser positivo y no superar el saldo pendiente', 'Ingresá un importe mayor a cero que no supere el saldo pendiente.'],
  ['Adjuntá un PDF, PNG o JPEG válido de hasta 2 MiB', 'Elegí un archivo PDF, PNG o JPEG válido de hasta 2 MiB.'],
]);

// Convierte un status HTTP (y el mensaje de negocio, si es uno conocido) en un UserFacingError.
// Las escrituras con 5xx/408 quedan marcadas como inciertas.
export function apiResponseError(status, body, { path = '', write = false } = {}) {
  const message = typeof body?.mensaje === 'string' ? body.mensaje : typeof body?.detail === 'string' ? body.detail : '';
  const uncertain = write && (status >= 500 || status === 408);
  const make = (text, kind = 'validation') => new UserFacingError(text, { status, kind, uncertain });
  if (status === 401) return make(path.split('?')[0] === '/api/auth/login' ? 'Revisá tu usuario y contraseña.' : path.startsWith('/api/chat-demo/') ? 'Volvé a abrir el chat para continuar.' : 'La sesión venció. Volvé a ingresar.');
  if (status === 403) return message === 'Origen de la solicitud no permitido' ? make(DEFAULT_ERROR_MESSAGE, 'request') : make('No tenés acceso a esta acción.');
  if (status === 429) return make('Recibimos muchos intentos. Esperá unos minutos antes de volver a intentar.');
  if (status === 413) return make('El archivo es demasiado grande. Elegí uno más pequeño.');
  if (status === 415) return make('Elegí un archivo PDF, PNG o JPEG.');
  if (status >= 400 && status < 500 && businessMessages.has(message)) return make(businessMessages.get(message));
  if (status === 409) return make('La información cambió o la acción ya no está disponible. Actualizá los datos y revisá el estado antes de continuar.');
  if (status === 422) return make('Revisá los datos ingresados y completá los campos requeridos.');
  if (status === 404) return make('No encontramos lo que buscás. Actualizá los datos e intentá nuevamente.');
  return make(uncertain ? CHECK_OPERATION_MESSAGE : DEFAULT_ERROR_MESSAGE, 'request');
}
