const CACHE_NAME = "portfolio-v5";
const SHELL_FILES = ["/", "/styles.css", "/app.js", "/manifest.json"];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE_NAME).then((c) => c.addAll(SHELL_FILES)));
    self.skipWaiting();
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    const url = new URL(e.request.url);

    // API requests: network only
    if (url.pathname.startsWith("/api/")) {
        return;
    }

    // App shell: cache first, fallback to network
    e.respondWith(
        caches.match(e.request).then((cached) => {
            return cached || fetch(e.request).then((res) => {
                if (res.ok) {
                    const clone = res.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(e.request, clone));
                }
                return res;
            });
        })
    );
});

self.addEventListener("push", (e) => {
    let data = { title: "Porteføljerapport", body: "Ny rapport er klar" };
    try {
        data = e.data.json();
    } catch (_) {}

    e.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: "/icon-192.png",
            badge: "/icon-192.png",
        })
    );
});

self.addEventListener("notificationclick", (e) => {
    e.notification.close();
    e.waitUntil(
        clients.matchAll({ type: "window" }).then((list) => {
            if (list.length > 0) return list[0].focus();
            return clients.openWindow("/");
        })
    );
});
