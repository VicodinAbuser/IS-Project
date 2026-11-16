// The backend API is always reached on the SAME address as the website, under /api:
//   * locally, the Angular dev server forwards /api to http://localhost:8000 (proxy.conf.json)
//   * on Vercel, frontend/vercel.json forwards /api to the laptop's ngrok address
// Same address = the login cookie is a normal first-party cookie and no CORS is needed.
export const environment = {
  production: true,
  apiUrl: '/api',
};
