"""Test setup: a throwaway database + data folder, and fakes for the two slow,
external pieces (the embedding vector store and the Groq LLM).

Everything else is the real code: routes, login, department rules, chunking,
BM25 search and RRF.

Run from the backend folder:
    pip install pytest httpx
    pytest -q
"""
import os
import tempfile

# Must be set BEFORE the app is imported (these are read at import time).
_TMP = tempfile.mkdtemp(prefix="mercury_test_")
os.environ["DATA_DIR"] = os.path.join(_TMP, "data")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["JWT_SECRET"] = "x" * 64
os.environ.pop("SMTP_HOST", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from app.rag import search as search_mod  # noqa: E402


class FakeVectorStore:
    """Stands in for Chroma: keeps documents in a list and applies the same
    filter format Chroma does (using our own matches())."""

    def __init__(self):
        self.docs: list[Document] = []

    def add_documents(self, docs, ids):
        for d, i in zip(docs, ids):
            self.docs.append(Document(page_content=d.page_content, metadata={**d.metadata, "chunk_id": i}))

    def similarity_search(self, query, k=10, filter=None):
        words = set(search_mod.tokenize(query))
        hits = [d for d in self.docs if search_mod.matches(d.metadata, filter)]
        # crude "similarity": shared words, so results are deterministic
        hits.sort(key=lambda d: -len(words & set(search_mod.tokenize(d.page_content))))
        return hits[:k]

    def reset_collection(self):
        self.docs = []


class _Reply:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """Answers instantly. The 'answer' echoes the context it was given, so tests
    can check exactly which chunks reached the model."""

    def __init__(self):
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        if isinstance(prompt, list):  # answer_question sends (role, text) pairs
            return _Reply("ANSWER FROM CONTEXT:\n" + prompt[-1][1])
        if "Rewrite the search query" in prompt:
            return _Reply("")  # no rewrites: keeps tests simple
        if "follow-up questions" in prompt:
            return _Reply("First follow-up?\nSecond follow-up?\nThird follow-up?")
        return _Reply("## Summary\n- a key point\n**Key takeaway:** it works")


@pytest.fixture()
def fakes(monkeypatch):
    store, llm = FakeVectorStore(), FakeLLM()
    import importlib

    chat = importlib.import_module("app.rag.chat")
    ingest = importlib.import_module("app.rag.ingest")

    monkeypatch.setattr(ingest, "get_vectorstore", lambda name: store)
    monkeypatch.setattr(search_mod, "get_vectorstore", lambda name: store)
    monkeypatch.setattr(search_mod, "get_llm", lambda t=0.0: llm)
    monkeypatch.setattr(chat, "get_llm", lambda t=0.0: llm)
    return store, llm


@pytest.fixture()
def app_client(fakes):
    """A fresh app with empty data, plus users in different departments."""
    import shutil

    from app.auth import create_access_token, hash_password
    from app.database import Base, SessionLocal, engine
    from app.main import app
    from app.models import DepartmentPolicy, User
    from app.rag.config import CHUNKS_DIR
    from app.routes import docsense

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(CHUNKS_DIR, ignore_errors=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    docsense._summary_cache.clear()

    db = SessionLocal()
    db.add_all([
        DepartmentPolicy(department="engineering", allowed_types="code,doc,wiki"),
        DepartmentPolicy(department="hr", allowed_types="doc,wiki"),
        DepartmentPolicy(department="marketing", allowed_types="wiki"),  # no docs!
    ])
    pw = hash_password("password-123")
    people = {
        "admin": User(name="Ada Admin", email="admin@co.com", password_hash=pw, department="engineering", role="admin"),
        "eng": User(name="Eli Eng", email="eli@co.com", password_hash=pw, department="engineering"),
        "hr": User(name="Hana HR", email="hana@co.com", password_hash=pw, department="hr"),
        "mkt": User(name="Max Mkt", email="max@co.com", password_hash=pw, department="marketing"),
    }
    db.add_all(people.values())
    db.commit()
    headers = {k: {"Authorization": f"Bearer {create_access_token(u)}"} for k, u in people.items()}
    db.close()

    client = TestClient(app)
    client.as_user = headers
    return client
