// SoulPulse Service Worker - PWA Offline Support
// Cache version - increment to invalidate old caches on update
const CACHE_VERSION = 'v1.0.0';
const STATIC_CACHE = `soulpulse-static-${CACHE_VERSION}`;
const APP_SHELL_CACHE = `soulpulse-shell-${CACHE_VERSION}`;

// App shell resources to pre-cache on install
const APP_SHELL_RESOURCES = [
  '/',
  '/index.html',
  '/flutter_bootstrap.js',
  '/main.dart.js',
  '/manifest.json',
  '/favicon.png',
  '/icons/Icon-192.png',
  '/icons/Icon-512.png',
];

// Patterns for static assets (cache-first)
const STATIC_ASSET_EXTENSIONS = [
  '.js',
  '.css',
  '.woff',
  '.woff2',
  '.ttf',
  '.otf',
  '.eot',
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.svg',
  '.webp',
  '.ico',
  '.json',
];

// Patterns to skip caching entirely (network-only)
const NETWORK_ONLY_PATTERNS = [
  '/api/',
  '/ws/',
  '/auth/',
];

// ─── INSTALL EVENT ───────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker:', CACHE_VERSION);
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then((cache) => {
      // Pre-cache app shell; don't fail install if some resources are missing
      return Promise.allSettled(
        APP_SHELL_RESOURCES.map((url) =>
          cache.add(url).catch((err) => {
            console.warn('[SW] Failed to pre-cache:', url, err);
          })
        )
      );
    }).then(() => {
      // Activate immediately without waiting for existing clients to close
      return self.skipWaiting();
    })
  );
});

// ─── ACTIVATE EVENT ──────────────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker:', CACHE_VERSION);
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => {
            // Delete old versioned caches
            return (
              (name.startsWith('soulpulse-static-') && name !== STATIC_CACHE) ||
              (name.startsWith('soulpulse-shell-') && name !== APP_SHELL_CACHE)
            );
          })
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    }).then(() => {
      // Take control of all open clients immediately
      return self.clients.claim();
    })
  );
});

// ─── FETCH EVENT ─────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) {
    return;
  }

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Network-only for API calls, WebSocket upgrades, auth endpoints
  if (NETWORK_ONLY_PATTERNS.some((pattern) => url.pathname.startsWith(pattern))) {
    return;
  }

  // Determine strategy based on resource type
  if (isStaticAsset(url.pathname)) {
    // Cache-first for static assets
    event.respondWith(cacheFirst(request));
  } else {
    // Network-first for navigation and other requests (app shell)
    event.respondWith(networkFirst(request));
  }
});

// ─── STRATEGIES ──────────────────────────────────────────────────────────────

/**
 * Cache-first strategy: serve from cache, fallback to network.
 * On network success, update the cache for next time.
 */
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) {
    return cached;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.warn('[SW] Cache-first fetch failed:', request.url, error);
    // Return a basic offline response for failed static assets
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

/**
 * Network-first strategy: try network, fallback to cache.
 * On network success, update the cache.
 */
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(APP_SHELL_CACHE);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    console.warn('[SW] Network-first fetch failed, trying cache:', request.url);
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    // For navigation requests, return cached index.html (SPA fallback)
    if (request.mode === 'navigate') {
      const fallback = await caches.match('/index.html');
      if (fallback) {
        return fallback;
      }
    }
    return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
  }
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

/**
 * Check if a pathname corresponds to a static asset based on extension.
 */
function isStaticAsset(pathname) {
  return STATIC_ASSET_EXTENSIONS.some((ext) => pathname.endsWith(ext));
}

// ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────
// Allow the app to communicate with the service worker (e.g., force update)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'CLEAR_CACHES') {
    caches.keys().then((names) => {
      names.forEach((name) => caches.delete(name));
    });
  }
});
