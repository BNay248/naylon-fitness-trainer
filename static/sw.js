const CACHE_NAME = 'trainer-shell-v1';
const PAGES = ['/', '/exercises', '/clients', '/coaches', '/profile', '/admin'];
const CORE_ASSETS = [
  ...PAGES,
  '/static/style.css',
  '/static/common.js',
  '/static/session-ui.js',
  '/static/offline.js',
  '/static/manifest.json',
  '/static/NFP.jpg',
  '/static/icon-192.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Network-first for everything we serve (so updates show up immediately when online),
// falling back to the cache so the app still opens with no connection.
self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return; // writes go through the page's own offline queue
  const url = new URL(request.url);
  if (url.origin !== location.origin || url.pathname.startsWith('/api/')) return; // app JS handles API offline fallback

  event.respondWith(
    fetch(request)
      .then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return res;
      })
      .catch(() => caches.match(request, { ignoreSearch: true }).then(cached => cached || (request.mode === 'navigate' ? caches.match('/') : undefined)))
  );
});
