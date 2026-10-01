const CACHE_NAME = "zorros-static-2026-09-01-v3";
const STATIC_ASSETS = [
  "/index.html",
  "/dashboard.html",
  "/ventas.html",
  "/productos.html",
  "/predicciones.html",
  "/usuarios.html",
  "/css/styles.css",
  "/js/api.js",
  "/js/ui.js",
  "/js/theme-init.js",
  "/js/auth.js",
  "/js/dashboard.js",
  "/js/ventas.js",
  "/js/productos.js",
  "/js/predicciones.js",
  "/js/usuarios.js",
  "/assets/icons.svg",
  "/assets/ZORROS%20LOGO.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key.startsWith("zorros-static-") && key !== CACHE_NAME).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

const PAGINAS = new Set(["/", "/index.html", "/dashboard.html", "/ventas.html", "/productos.html", "/predicciones.html", "/usuarios.html"]);

function esRecursoEstatico(request) {
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  return ["/css/", "/js/", "/assets/"].some((prefijo) => url.pathname.startsWith(prefijo));
}

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);

  if (event.request.mode === "navigate" && url.origin === self.location.origin && PAGINAS.has(url.pathname)) {
    event.respondWith(
      fetch(event.request)
        .then(async (response) => {
          if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            await cache.put(event.request, response.clone());
          }
          return response;
        })
        .catch(() => caches.match(url.pathname === "/" ? "/index.html" : event.request))
    );
    return;
  }

  if (!esRecursoEstatico(event.request)) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const refresh = fetch(event.request)
        .then(async (response) => {
          if (response.ok) {
            const cache = await caches.open(CACHE_NAME);
            await cache.put(event.request, response.clone());
          }
          return response;
        })
        .catch(() => cached);

      if (cached) {
        event.waitUntil(refresh);
        return cached;
      }
      return refresh;
    })
  );
});
