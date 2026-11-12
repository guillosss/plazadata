// Service worker de PlazaData: permite instalar la app y verla sin conexión con los últimos datos guardados.
const VERSION = "pd-v2";
const BASE = ["/", "/static/app.css", "/static/app.js", "/manifest.webmanifest", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(BASE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

const guardar = (req, resp) => { if (resp && resp.ok) { const copia = resp.clone(); caches.open(VERSION).then((c) => c.put(req, copia)); } return resp; };
// Copia guardada de una respuesta de la API, marcada para que el panel avise que no son datos frescos.
const desdeCache = async (req) => {
  const c = await caches.match(req);
  if (!c) return null;
  const h = new Headers(c.headers); h.set("X-Desde-Cache", "1");
  return new Response(c.body, { status: c.status, statusText: c.statusText, headers: h });
};
const sinDatos = () => new Response(JSON.stringify({ detail: "Sin conexión" }), { status: 503, headers: { "Content-Type": "application/json" } });

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;                       // los registros de uso y comentarios no se interceptan
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/admin") || url.pathname.startsWith("/admin")) return;   // nunca guardar el resumen privado

  if (url.pathname.startsWith("/api/")) {
    // Datos: primero la red. Sin conexión, o si el servidor falla (5xx), el último dato guardado.
    e.respondWith(fetch(req).then(async (r) => {
      if (r.status >= 500) return (await desdeCache(req)) || r;
      return guardar(req, r);
    }).catch(async () => (await desdeCache(req)) || sinDatos()));
    return;
  }
  // Archivos de la app: primero la red (así las actualizaciones llegan), con la copia guardada de respaldo.
  e.respondWith(fetch(req).then((r) => guardar(req, r)).catch(() => caches.match(req)));
});
