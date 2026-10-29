export const ORDER_POLL_MS = 5000;

/** Una consulta a la vez; no descarga el tablero si su huella no cambió. */
export function createOrderPoller({ readRevision, refresh, enabled, onError, clock = Date.now }) {
  let controller = null;
  let revision = null;
  let lastDownload = 0;
  let nextAttempt = 0;
  let failures = 0;
  let forbidden = false;
  return {
    async update() {
      if (!enabled() || controller || forbidden || clock() < nextAttempt) return;
      const request = new AbortController();
      controller = request;
      try {
        const current = await readRevision(request.signal);
        if (request.signal.aborted) return;
        if (typeof current !== 'string' || !current) throw new Error('Revisión inválida');
        // La reconciliación periódica también cubre cambios fuera de los flujos normales.
        if (revision !== current || failures > 0 || clock() - lastDownload >= 60000) {
          const accepted = await refresh(request.signal);
          if (request.signal.aborted) return;
          if (accepted !== false) { revision = current; lastDownload = clock(); }
        }
        failures = 0;
        nextAttempt = 0;
      } catch (error) {
        if (!request.signal.aborted) {
          failures += 1;
          nextAttempt = clock() + Math.min(60000, ORDER_POLL_MS * 2 ** Math.min(failures, 4));
          forbidden = [401, 403].includes(error.status);
          onError(error);
        }
      } finally {
        if (controller === request) controller = null;
      }
    },
    pause() { controller?.abort(); },
  };
}
