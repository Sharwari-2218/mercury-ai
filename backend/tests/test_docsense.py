"""Docsense + Databloom: upload, list, ask, chunks, summarize, and who may see what."""
import io

from app.rag.search import combine_filters, matches

LEAVE = ("Leave policy. Every employee gets 12 sick days per year. "
         "Sick days do not carry over to the next year. ") * 30
DEPLOY = ("Deploy guide. Run the deploy script from the main branch. "
          "Staging deploys need approval from the platform lead. ") * 30


def upload(client, who, name, text, **extra):
    return client.post(
        "/docsense/upload",
        files={"file": (name, io.BytesIO(text.encode()), "text/plain")},
        data=extra,
        headers=client.as_user[who],
    )


# ---------- The filter checker used by BM25 ----------

def test_matches_understands_chroma_filters():
    meta = {"type": "doc", "department": "hr", "doc_id": "a"}
    assert matches(meta, None)
    assert matches(meta, {"type": "doc"})
    assert not matches(meta, {"type": "wiki"})
    assert matches(meta, {"type": "doc", "doc_id": "a"})
    assert matches(meta, {"department": {"$in": ["hr", "all"]}})
    assert not matches(meta, {"department": {"$in": ["engineering", "all"]}})
    assert matches(meta, {"$and": [{"type": "doc"}, {"department": {"$in": ["hr"]}}]})
    assert not matches(meta, {"$and": [{"type": "doc"}, {"doc_id": "b"}]})
    assert matches(meta, {"$or": [{"doc_id": "b"}, {"doc_id": "a"}]})


def test_combine_filters_skips_empty():
    assert combine_filters(None, None) is None
    assert combine_filters({"a": 1}, None) == {"a": 1}
    assert combine_filters({"a": 1}, {"b": 2}) == {"$and": [{"a": 1}, {"b": 2}]}


# ---------- Login and permissions ----------

def test_every_route_needs_login(app_client):
    c = app_client
    assert c.get("/docsense/files").status_code == 401
    assert c.post("/docsense/ask", json={"question": "hi"}).status_code == 401
    assert c.get("/databloom/abc/chunks").status_code == 401
    assert c.post("/databloom", json={"doc_id": "a", "chunk_id": "b"}).status_code == 401
    r = c.post("/docsense/upload", files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")})
    assert r.status_code == 401


def test_department_without_doc_permission_is_blocked(app_client):
    r = app_client.get("/docsense/files", headers=app_client.as_user["mkt"])
    assert r.status_code == 403


# ---------- Upload ----------

def test_upload_takes_department_from_login_not_form(app_client):
    r = upload(app_client, "eng", "leave.txt", LEAVE, department="hr", uploaded_by="someone-else")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["department"] == "engineering"
    assert body["chunks"] > 1
    files = app_client.get("/docsense/files", headers=app_client.as_user["eng"]).json()
    assert files[0]["uploaded_by"] == "Eli Eng"


def test_upload_rejects_bad_files(app_client):
    assert upload(app_client, "eng", "virus.exe", "x").status_code == 400
    assert upload(app_client, "eng", "empty.txt", "").status_code == 400
    assert upload(app_client, "eng", "blank.txt", "   \n  ").status_code == 422  # no text inside


def test_upload_docx(app_client):
    import docx

    d = docx.Document()
    d.add_paragraph("Expense policy: meals up to 500 rupees per day are reimbursed.")
    buf = io.BytesIO()
    d.save(buf)
    buf.seek(0)
    r = app_client.post("/docsense/upload", files={"file": ("expenses.docx", buf)},
                        headers=app_client.as_user["hr"])
    assert r.status_code == 200, r.text


# ---------- Listing ----------

def test_files_only_shows_your_department(app_client):
    eng_doc = upload(app_client, "eng", "deploy.md", DEPLOY).json()["doc_id"]
    hr_doc = upload(app_client, "hr", "leave.txt", LEAVE).json()["doc_id"]

    def ids(who):
        return {f["doc_id"] for f in app_client.get("/docsense/files", headers=app_client.as_user[who]).json()}

    assert ids("eng") == {eng_doc}
    assert ids("hr") == {hr_doc}
    assert ids("admin") == {eng_doc, hr_doc}


# ---------- Asking ----------

def test_ask_one_document_only_uses_that_document(app_client):
    leave = upload(app_client, "eng", "leave.txt", LEAVE).json()["doc_id"]
    upload(app_client, "eng", "deploy.md", DEPLOY)

    r = app_client.post("/docsense/ask", json={"question": "how many sick days", "doc_id": leave},
                        headers=app_client.as_user["eng"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"], "expected at least one source"
    assert {s["source"] for s in body["sources"]} == {"leave.txt"}
    assert "Deploy guide" not in body["answer"]
    assert len(body["suggestions"]) == 3


def test_cannot_ask_about_another_departments_document(app_client):
    eng_doc = upload(app_client, "eng", "deploy.md", DEPLOY).json()["doc_id"]
    r = app_client.post("/docsense/ask", json={"question": "deploy", "doc_id": eng_doc},
                        headers=app_client.as_user["hr"])
    assert r.status_code == 404


def test_ask_all_documents_still_hides_other_departments(app_client):
    upload(app_client, "eng", "deploy.md", DEPLOY)
    upload(app_client, "hr", "leave.txt", LEAVE)
    r = app_client.post("/docsense/ask", json={"question": "deploy script staging approval sick days"},
                        headers=app_client.as_user["hr"])
    assert r.status_code == 200
    assert "Deploy guide" not in r.json()["answer"]
    assert {s["source"] for s in r.json()["sources"]} <= {"leave.txt"}


def test_ask_validates_question(app_client):
    r = app_client.post("/docsense/ask", json={"question": ""}, headers=app_client.as_user["eng"])
    assert r.status_code == 422


def test_ask_when_llm_is_down_gives_clear_error(app_client, fakes):
    _, llm = fakes
    upload(app_client, "eng", "leave.txt", LEAVE)

    def broken(prompt):
        if isinstance(prompt, list):
            raise RuntimeError("rate limited")
        return type("R", (), {"content": ""})()

    llm.invoke = broken
    r = app_client.post("/docsense/ask", json={"question": "sick days"}, headers=app_client.as_user["eng"])
    assert r.status_code == 502
    assert "try again" in r.json()["detail"]


# ---------- Databloom ----------

def test_chunks_come_back_in_order(app_client):
    doc = upload(app_client, "eng", "leave.txt", LEAVE).json()
    r = app_client.get(f"/databloom/{doc['doc_id']}/chunks", headers=app_client.as_user["eng"])
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "leave.txt"
    assert body["count"] == doc["chunks"] == len(body["chunks"])
    assert [c["index"] for c in body["chunks"]] == list(range(body["count"]))
    assert app_client.get(f"/databloom/{doc['doc_id']}/chunks", headers=app_client.as_user["hr"]).status_code == 404


def test_summarize_chunk_and_cache(app_client, fakes):
    _, llm = fakes
    doc_id = upload(app_client, "eng", "leave.txt", LEAVE).json()["doc_id"]
    chunk_id = app_client.get(f"/databloom/{doc_id}/chunks", headers=app_client.as_user["eng"]).json()["chunks"][0]["chunk_id"]

    r1 = app_client.post("/databloom", json={"doc_id": doc_id, "chunk_id": chunk_id}, headers=app_client.as_user["eng"])
    assert r1.status_code == 200, r1.text
    assert r1.json()["summary"].startswith("## Summary")
    assert r1.json()["cached"] is False

    calls = llm.calls
    r2 = app_client.post("/databloom", json={"doc_id": doc_id, "chunk_id": chunk_id}, headers=app_client.as_user["eng"])
    assert r2.json()["cached"] is True
    assert llm.calls == calls  # no second LLM call


def test_summarize_blocks_other_departments_and_wrong_doc(app_client):
    eng = upload(app_client, "eng", "deploy.md", DEPLOY).json()["doc_id"]
    other = upload(app_client, "eng", "leave.txt", LEAVE).json()["doc_id"]
    chunk_id = app_client.get(f"/databloom/{eng}/chunks", headers=app_client.as_user["eng"]).json()["chunks"][0]["chunk_id"]

    hr = app_client.post("/databloom", json={"doc_id": eng, "chunk_id": chunk_id}, headers=app_client.as_user["hr"])
    assert hr.status_code == 404
    wrong_doc = app_client.post("/databloom", json={"doc_id": other, "chunk_id": chunk_id}, headers=app_client.as_user["eng"])
    assert wrong_doc.status_code == 404
    made_up = app_client.post("/databloom", json={"doc_id": eng, "chunk_id": "nope"}, headers=app_client.as_user["eng"])
    assert made_up.status_code == 404
