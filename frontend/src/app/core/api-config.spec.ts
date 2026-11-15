import { environment } from '../../environments/environment';
import { apiUrl, isDefaultApiUrl, normalizeApiUrl, setApiUrl } from './api-config';

describe('api-config', () => {
  afterEach(() => setApiUrl(null));

  it('normalises tunnel addresses to the /api base', () => {
    expect(normalizeApiUrl('abc.trycloudflare.com')).toBe('https://abc.trycloudflare.com/api');
    expect(normalizeApiUrl('https://me.ngrok-free.app/')).toBe('https://me.ngrok-free.app/api');
    expect(normalizeApiUrl('http://localhost:8000/api')).toBe('http://localhost:8000/api');
  });

  it('uses a saved address, and falls back to the build default after reset', () => {
    setApiUrl('https://abc.trycloudflare.com');
    expect(apiUrl()).toBe('https://abc.trycloudflare.com/api');
    expect(isDefaultApiUrl()).toBeFalse();
    setApiUrl(null);
    expect(apiUrl()).toBe(environment.apiUrl);
  });
});
