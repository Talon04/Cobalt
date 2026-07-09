const CACHE_NAME = "cobalt-static-v2";
const ASSETS = [
    "/",
    "/static/styles.css",
    "/static/app.js",
    "/static/manage-models.js",
    "/static/settings.js",
    "/static/vendor/marked.min.js",
    "/static/vendor/purify.min.js",
    "/static/vendor/katex.min.css",
    "/static/vendor/katex.min.js",
    "/static/vendor/katex-auto-render.min.js",
    "/manifest.webmanifest",
    "/static/icon-192.png",
    "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
    );
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;
    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request)
                .then((response) => {
                    if (!response || response.status !== 200) return response;
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return response;
                })
                .catch(() => caches.match("/"));
        })
    );
});
