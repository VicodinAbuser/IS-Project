# Hosting the website on Vercel (backend + Oracle stay on your laptop)

```
Anyone's browser ──► https://your-app.vercel.app          (Angular website, hosted by Vercel)
        │
        └── API calls ──► https://xyz.trycloudflare.com    (tunnel: a public address for your laptop)
                              └──► your laptop: FastAPI :8000 ──► Oracle :1521
```

- **Vercel** only hosts the website files (HTML/JS/CSS). It never talks to Oracle.
- The **browser** calls your backend through a **tunnel**: a free service that gives the backend on your laptop a public `https://` address without changing router or firewall settings. Only the API is exposed. Oracle itself stays private on the laptop.
- Every change made on the website is saved in Oracle on your laptop, and shows up straight away in SQL Developer. The reverse is true as well.
- **Your laptop must be on**, running Oracle, the backend and the tunnel, whenever someone uses the site.

---

## Part 1: Put the website on Vercel (one-time, about 10 minutes)

1. Sign in at **vercel.com** with your GitHub account.
2. **Add New → Project**, then pick the **IS-Project** repository and click **Import**.
3. On the configuration screen:
   - **Root Directory**: click *Edit* and choose **`frontend`** ← important
   - Framework, build command and output folder are read from `frontend/vercel.json`, so leave them as they are
   - **Environment Variables** (optional, see Part 3): `API_URL` = your tunnel address
4. Click **Deploy**. After a minute or two you get a link like `https://is-project-xyz.vercel.app`.

From now on, every `git push` to GitHub redeploys the site automatically.

## Part 2: Start everything on the laptop (each time you want the site to work)

> **Shortcut (ngrok with a static domain):** in `run-local\oracle21c` or `run-local\oracle26ai`, double-click **`START-ONLINE.bat`**. It starts the backend and the ngrok tunnel together, so you can skip the manual steps below.

You need three windows:

**Window 1: backend**
```powershell
cd backend
.venv\Scripts\activate
uvicorn app.main:app
```

**Window 2: tunnel.** Pick **one** of the two tunnels below.

### Option 1: Cloudflare Quick Tunnel (no account needed)
Install once:
```powershell
winget install --id Cloudflare.cloudflared
```
Then each time:
```powershell
cloudflared tunnel --url http://localhost:8000
```
It prints an address like `https://random-words-1234.trycloudflare.com`. Keep this window open.
**The address is different every time you start it.**

### Option 2: ngrok (free account, address never changes)
1. Sign up at ngrok.com, install ngrok, and run the `ngrok config add-authtoken ...` command shown on your dashboard (once).
2. On the ngrok dashboard, claim your **free static domain** (e.g. `your-name.ngrok-free.app`).
3. Each time, start the tunnel to port **8000** using the command the dashboard shows for that domain. It looks like:
   ```powershell
   ngrok http --url=your-name.ngrok-free.app 8000
   ```

Oracle runs as a Windows service, so it's already running. SQL Developer can stay open as usual.

## Part 3: Point the website at your tunnel

**With a fixed address (ngrok static domain), set it once:** in Vercel go to **Project → Settings → Environment Variables**, add `API_URL` = `https://your-name.ngrok-free.app`, then **Deployments → ⋯ → Redeploy**. Done for good.

**With a changing address (Cloudflare Quick Tunnel), share a link instead.** Add `?api=` and the tunnel address to your Vercel link:
```
https://is-project-xyz.vercel.app/?api=https://random-words-1234.trycloudflare.com
```
Opening that link saves the backend address in that browser, so nothing needs rebuilding.

You can also set or check the address on the **login page**. At the bottom it shows **Backend: …** with **Test** and **Change**:

| Test result | Meaning |
|---|---|
| connected to Oracle | Everything works |
| backend up, Oracle not reachable | Start Oracle on the laptop (Windows Services → Oracle…) |
| backend not reachable | The backend window or the tunnel window isn't running, or the address is wrong |

## Before you share the link publicly
Your backend is now reachable from the internet, so:
1. **Set a private JWT secret.** Copy `backend/.env.example` to `backend/.env` and replace `JWT_SECRET` with any long random text. Restart the backend.
2. **Change the admin password**, because `admin123` is printed in the README. Make a new hash:
   ```powershell
   cd backend
   .venv\Scripts\python -c "import bcrypt; print(bcrypt.hashpw(b'YourNewPassword', bcrypt.gensalt()).decode())"
   ```
   Then in SQL Developer (INVENTORY connection):
   ```sql
   UPDATE app_users SET password_hash = '<paste the hash>' WHERE email = 'admin@inventory.com';
   COMMIT;
   ```
3. Stop the tunnel (Ctrl+C) when you don't need the site to be reachable.

## For the classroom
If the college Wi-Fi is unreliable, you can still run the whole thing locally (http://localhost:4200) as described in the README. Nothing changes in the code.
