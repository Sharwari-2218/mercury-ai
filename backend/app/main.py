"""Example main.py. Merge the marked parts into your existing one."""
import os

from dotenv import load_dotenv

load_dotenv()  # must run before importing app.auth (it reads JWT_SECRET)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .database import Base, engine  # noqa: E402
from .routes import auth_routes, example_protected  # noqa: E402

Base.metadata.create_all(engine)

app = FastAPI(
    title="Mercury AI",
    # Hide the API docs in production: set ENV=production in .env
    docs_url=None if os.getenv("ENV") == "production" else "/docs",
    redoc_url=None,
)

# Only needed if the frontend calls the backend directly on another origin.
# With the Vite proxy (dev) or nginx (Docker) everything is same-origin and this is unused.
FRONTEND_ORIGINS = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,   # exact origins, never "*" with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_routes.router)
app.include_router(example_protected.router)  # replace with your real routers


@app.get("/health")
def health():
    return {"ok": True}
