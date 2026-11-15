// Runs before "ng build". On Vercel, set the environment variable API_URL
// (e.g. https://your-name.ngrok-free.app) and it becomes the site's default backend.
// Without API_URL nothing changes, so local builds keep http://localhost:8000/api.
import { writeFileSync } from 'node:fs';

const raw = (process.env.API_URL || '').trim();
if (raw) {
  let url = raw.replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  if (!url.endsWith('/api')) url += '/api';
  writeFileSync(new URL('../src/environments/environment.ts', import.meta.url),
    `export const environment = {\n  production: true,\n  apiUrl: '${url}',\n};\n`);
  console.log(`Backend API for this build: ${url}`);
} else {
  console.log('API_URL not set: using src/environments/environment.ts as is');
}
