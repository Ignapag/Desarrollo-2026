// Una sola solicitud y una instantánea compartida por la campanita y la bandeja.
// La cancelación invalida respuestas incluso cuando el transporte ignora AbortSignal.
export function createInboxResource(fetchInbox, validate = (value) => value) {
  let snapshot = { data: null, loading: false, error: false };
  let request = null;
  let revision = 0;
  const listeners = new Set();
  const publish = (next) => { snapshot = next; for (const listener of listeners) listener(); };
  const resource = {
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot: () => snapshot,
    cancel() { revision += 1; request?.controller.abort(); request = null; },
    load: (force = false) => {
      if (request) return request.promise;
      if (!force && snapshot.data && !snapshot.error) return Promise.resolve(snapshot.data);
      const entry = { controller: new AbortController(), revision };
      request = entry;
      publish({ ...snapshot, loading: true });
      entry.promise = Promise.resolve().then(() => fetchInbox(entry.controller.signal)).then(validate).then((data) => {
        if (request === entry && revision === entry.revision) publish({ data, loading: false, error: false });
        return data;
      }).catch((error) => {
        if (request === entry && revision === entry.revision) publish({ data: [401, 403].includes(error.status) ? null : snapshot.data, loading: false, error: true });
        throw error;
      }).finally(() => { if (request === entry) request = null; });
      return entry.promise;
    },
  };
  return resource;
}
