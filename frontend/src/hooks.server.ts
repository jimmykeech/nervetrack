// In production (adapter-node) there is no Vite dev proxy, so the Node server
// forwards /api/* requests to the backend. In dev, Vite's proxy handles /api
// before this hook runs, so this is a no-op there.

import type { Handle } from '@sveltejs/kit';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://backend:8000';

export const handle: Handle = async ({ event, resolve }) => {
  if (event.url.pathname.startsWith('/api')) {
    const target = BACKEND_URL + event.url.pathname + event.url.search;
    const init: RequestInit = {
      method: event.request.method,
      headers: event.request.headers,
      // Do not follow redirects server-side: the OAuth 302s (and their
      // Set-Cookie headers) must reach the browser intact.
      redirect: 'manual'
    };
    if (!['GET', 'HEAD'].includes(event.request.method)) {
      init.body = await event.request.arrayBuffer();
    }
    return fetch(target, init);
  }
  return resolve(event);
};
