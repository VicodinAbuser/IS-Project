"""Application (business) tier entry point. Run: uvicorn app.main:app --reload

Layers inside this backend:
  routers/   the REST API endpoints (/api/...) the Angular website calls: read the request,
             check the login and permission, call a service, return JSON
  services/  the business logic (rules), one database transaction per action
  database.py / INVENTORY_PKG   the data operations in Oracle
"""
from contextlib import asynccontextmanager

import oracledb
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import close_pool, get_db, init_pool, oracle_error_to_http, query_one
from .errors import BusinessError
from .routers import auth, catalog, inventory, orders, reports, users


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()          # open the Oracle connection pool when the server starts
    yield
    close_pool()


app = FastAPI(
    title="Inventory Management System API",
    description="3-tier IS project: Angular UI -> FastAPI (this: business logic) -> Oracle Database (tables, "
                "procedures, triggers). Log in with the Authorize button to try the protected endpoints.",
    version="3.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------- security headers
# Sent with every response. The website (Vercel / Angular dev server) sends its own set too.
API_HEADERS = {
    "X-Content-Type-Options": "nosniff",                       # browser must not guess file types
    "X-Frame-Options": "DENY",                                 # can't be shown inside a frame (clickjacking)
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",   # HTTPS only (ignored on http://localhost)
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # The old "XSS filter" header is deprecated and can itself be abused, so OWASP recommends
    # turning it off ("0") and relying on Content-Security-Policy instead.
    "X-XSS-Protection": "0",
}
# The API only returns data (JSON / files), never pages, so it may load nothing at all.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
# Swagger /docs is a page that loads its scripts from a CDN.
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in API_HEADERS.items():
        response.headers.setdefault(name, value)
    docs = request.url.path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")
    response.headers.setdefault("Content-Security-Policy", DOCS_CSP if docs else API_CSP)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")       # personal data: don't keep copies
    return response


if settings.cors_origins:      # only needed if a website on ANOTHER address calls the API directly
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-Requested-With", "Authorization"],
                       expose_headers=["Content-Disposition"])


# ---------------------------------------------------------------- errors -> clean JSON
@app.exception_handler(BusinessError)
async def business_errors(_: Request, exc: BusinessError):
    """A business rule in app/services said no (e.g. not enough stock -> 409)."""
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


@app.exception_handler(oracledb.DatabaseError)
async def oracle_errors(_: Request, exc: oracledb.DatabaseError):
    """Oracle refused a change (e.g. duplicate email, stock below 0) -> clean HTTP error."""
    http = oracle_error_to_http(exc)
    if http is None:
        raise exc
    return JSONResponse(status_code=http.status_code, content={"detail": http.detail})


for r in (auth, users, catalog, inventory, orders, reports):
    app.include_router(r.router)


@app.get("/api/health", tags=["Health"])
def health():
    """Public check that the API is up AND Oracle answers a query. It says only "ok" or "error":
    the database name, address and version are not shown to the public (staff see them on the dashboard)."""
    session = get_db()
    try:
        conn = next(session)
        query_one(conn, "SELECT 1 AS ok FROM dual")
    except oracledb.Error as exc:
        print(f"Health check: cannot reach Oracle at {settings.oracle_dsn}: {str(exc).splitlines()[0]}")
        return JSONResponse(status_code=503, content={"status": "error", "detail": "Service temporarily unavailable"})
    finally:
        session.close()
    return {"status": "ok"}
