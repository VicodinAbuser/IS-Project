"""Application (business) tier entry point. Run: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

import oracledb
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import close_pool, get_db, init_pool, oracle_error_to_http, query_one
from .routers import auth, catalog, inventory, orders, reports


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_pool()          # open the Oracle connection pool when the server starts
    yield
    close_pool()


app = FastAPI(
    title="Inventory Management System API",
    description="3-tier IS project: Angular UI -> FastAPI (this) -> Oracle AI Database 26ai (PL/SQL)",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow the Angular site (local dev server or Vercel) to call this API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_origin_regex=settings.cors_origin_regex, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])


@app.exception_handler(oracledb.DatabaseError)
async def oracle_errors(_: Request, exc: oracledb.DatabaseError):
    """Errors raised inside PL/SQL (e.g. ORA-20001 not enough stock) become clean HTTP errors."""
    http = oracle_error_to_http(exc)
    if http is None:
        raise exc
    return JSONResponse(status_code=http.status_code, content={"detail": http.detail})


for r in (auth, catalog, inventory, orders, reports):
    app.include_router(r.router)


@app.get("/api/health", tags=["Health"])
def health():
    """Checks the whole chain: this API is up AND Oracle answers a query."""
    session = get_db()
    try:
        conn = next(session)
        db_version = query_one(conn, "SELECT version_full FROM product_component_version WHERE ROWNUM = 1")
    except oracledb.Error as exc:
        return JSONResponse(status_code=503, content={
            "status": "error", "database": settings.oracle_dsn,
            "detail": f"API is running but cannot reach Oracle: {str(exc).splitlines()[0]}"})
    finally:
        session.close()
    return {"status": "ok", "database": settings.oracle_dsn, "oracle_version": db_version["version_full"]}
