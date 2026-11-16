# Online with Vercel (backend + Oracle stay on your laptop)

```
Anyone's browser ──► https://is-project-inventory.vercel.app            website (Angular), hosted by Vercel
                        │  /api/...  (same address)
                        ▼
                     Vercel forwards /api to  https://<your-name>.ngrok-free.dev/api/...   (frontend/vercel.json)
                        ▼
                     ngrok tunnel  ──►  YOUR LAPTOP: FastAPI :8000  ──►  Oracle :1521
```

- **Vercel** hosts the website files and forwards every `/api/...` request to your laptop's fixed ngrok address.
  The browser only ever talks to the Vercel address, so the login cookie is an ordinary first-party,
  **HttpOnly + Secure + SameSite=Strict** cookie and no cross-site (CORS) setup is needed.
- **ngrok** gives the backend on your laptop a fixed public `https://` address. Only the API is exposed;
  Oracle itself stays private on the laptop.
- Everything changed on the website is saved in Oracle on your laptop, and shows up straight away in SQL Developer.
- **Your laptop must be on**, running the backend and the tunnel (`START-ONLINE.bat`), whenever someone uses the site.

---

## One-time setup

### 1. ngrok (free, fixed address)
1. Sign up at **ngrok.com** → **Share Localhost** → follow the Windows install steps, and run the
   `ngrok config add-authtoken ...` command it shows (once).
2. Your free static domain is shown in step 3 of that page or under **Domains**, e.g. `monotone-handball-bulldozer.ngrok-free.dev`.

### 2. Point the website at your ngrok address
In **`frontend/vercel.json`**, the first rewrite sends `/api` to the laptop:
```json
{ "source": "/api/:path*", "destination": "https://monotone-handball-bulldozer.ngrok-free.dev/api/:path*" }
```
If your ngrok domain is different, change that line, then commit and push to GitHub.

### 3. Vercel
1. Sign in at **vercel.com** with the GitHub account that owns the repository.
2. **Add New → Project** → import **IS-Project** → choose **Import single project** for the **`frontend`** folder
   (Root Directory `frontend`). Don't import the backend: it runs on the laptop.
3. **Deploy**. The project's link (under **Domains**) is the one to share, e.g. `https://is-project-inventory.vercel.app`.
   (An `API_URL` environment variable from an earlier version is no longer used and can be deleted.)

From now on, every `git push` to GitHub redeploys the website automatically.

## Each time the site should be online
Double-click **`START-ONLINE.bat`** (in `run-local\oracle21c` or `run-local\oracle26ai`). It starts the backend
(unless `START-APP.bat` already did) and the ngrok tunnel. Keep both windows open. To go offline: Ctrl+C in the ngrok window.

Check: open your Vercel link. The login page shows **Server: connected to Oracle**.

| Login page shows | Meaning |
|---|---|
| connected to Oracle | Everything works |
| backend up, Oracle not reachable | Start Oracle on the laptop (Windows Services → OracleServiceORCL) |
| backend not reachable | `START-ONLINE.bat` isn't running, the laptop is asleep, or the domain in `vercel.json` is wrong |

## Security of the public link
- Sessions are HttpOnly cookies; changes need the `X-Requested-With` header (CSRF protection);
  5 wrong passwords lock an account for 15 minutes.
- `START-ONLINE.bat` creates a private `JWT_SECRET` in `backend\.env` the first time.
- The demo passwords (`admin123`, `customer123`) are printed in this README. Before sharing the link widely,
  give the staff accounts new passwords, or disable the demo accounts in **Users & access**.
- The website sends strict security headers (Content-Security-Policy, X-Frame-Options, HSTS, ...) from `vercel.json`;
  the API sends its own from `backend/app/main.py`.
