import { environment } from '../../environments/environment';

/**
 * Where the backend API lives.
 *   1. A link like https://your-app.vercel.app/?api=https://abc.trycloudflare.com saves that address.
 *   2. Otherwise the address saved earlier (from a link or the login page) is used.
 *   3. Otherwise the build-time default from environment.ts (http://localhost:8000/api).
 * So when the tunnel address changes you share a new link instead of rebuilding the site.
 */
const KEY = 'ims_api_url';

export function normalizeApiUrl(url: string): string {
  let u = url.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(u)) u = 'https://' + u;
  return u.endsWith('/api') ? u : u + '/api';
}

export function apiUrl(): string {
  try {
    return localStorage.getItem(KEY) || environment.apiUrl;
  } catch {
    return environment.apiUrl;
  }
}

export function setApiUrl(url: string | null): void {
  try {
    url ? localStorage.setItem(KEY, normalizeApiUrl(url)) : localStorage.removeItem(KEY);
  } catch { /* storage blocked: fall back to the default */ }
}

export function isDefaultApiUrl(): boolean {
  return apiUrl() === environment.apiUrl;
}

/** Called once at startup: picks up ?api=... from the address bar, then removes it from the URL. */
export function captureApiUrlFromLink(): void {
  const params = new URLSearchParams(window.location.search);
  const api = params.get('api');
  if (!api) return;
  setApiUrl(api);
  params.delete('api');
  const rest = params.toString();
  history.replaceState(null, '', window.location.pathname + (rest ? '?' + rest : '') + window.location.hash);
}
