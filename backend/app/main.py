"""Application (business) tier entry point. Run: uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import auth, catalog, inventory, orders, reports

Base.metadata.create_all(bind=engine)  # creates tables on first run

app = FastAPI(
    title="Inventory Management System API",
    description="3-tier IS project: Angular UI -> FastAPI (this) -> SQL database",
    version="1.0.0",
)

# Allow the Angular dev server (a different origin) to call this API from the browser.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

for r in (auth, catalog, inventory, orders, reports):
    app.include_router(r.router)


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok"}
