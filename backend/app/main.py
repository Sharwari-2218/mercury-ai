"""Mercury AI FastAPI app."""
import os

from dotenv import load_dotenv

load_dotenv()  # must run before importing app.auth (it reads JWT_SECRET)

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from .database import Base, engine  # noqa: E402
from .routes import (  # noqa: E402
    ask, auth_routes, contribute, databloom, docsense, feed, gittalk, sharebase,
)

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
app.include_router(ask.router)          # POST /ask ("All" mode)
app.include_router(gittalk.router)      # /gittalk/index, /gittalk/ask, /gittalk/repos
app.include_router(docsense.router)     # /docsense/upload, /docsense/ask, /docsense/files
app.include_router(sharebase.router)    # /sharebase/add, /sharebase/ask, /sharebase/pages
app.include_router(databloom.router)    # /databloom/files, /databloom/chunks, POST /databloom
app.include_router(contribute.router)   # /contribute, /contribute/status/{id}, /contribute/jobs
app.include_router(feed.router)         # /feed, /feed/trending, /posts, /posts/{id}/vote, /subscriptions


@app.get("/health")
def health():
    return {"ok": True}
