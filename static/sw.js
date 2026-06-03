// PantryAI Service Worker
// Bump CACHE_NAME whenever static assets change to force update.
const CACHE_NAME = 'pantryai-v1';
const OFFLINE_URL = '/static/offline.html';

// Assets to precache on install (must all succeed, so keep this small)
const PRECACHE_URLS = [
  OFFLINE_URL,
  '/static/manifest.webmanifest',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/apple-touch-icon.png',
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())   // activate immediately
  );
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())  // take over open tabs right away
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle GET requests
  if (request.method !== 'GET') return;

  // ① API calls — network only, never cache
  if (url.pathname.startsWith('/api/')) return;

  // ② Static assets + Google Fonts — cache first, then network
  const isStaticAsset = url.pathname.startsWith('/static/');
  const isFont = url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';

  if (isStaticAsset || isFont) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(resp => {
          if (resp.ok) {
            const clone = resp.clone();
            caches.open(CACHE_NAME).then(c => c.put(request, clone));
          }
          return resp;
        });
      })
    );
    return;
  }

  // ③ HTML pages (/, /login, etc.) — network first, cache fallback, offline fallback
  event.respondWith(
    fetch(request)
      .then(resp => {
        // Cache a fresh copy on success
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return resp;
      })
      .catch(() =>
        caches.match(request)
          .then(cached => cached || caches.match(OFFLINE_URL))
      )
  );
});
