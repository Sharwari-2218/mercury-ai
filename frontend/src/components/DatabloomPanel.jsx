// frontend/src/components/DatabloomPanel.jsx
// Rendered on the Ask page when the "Databloom" mode is selected.
// Requires: npm install react-markdown
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

// "/api" goes through the Vite proxy -> http://localhost:8000 (prefix stripped).
const API = import.meta.env.VITE_API_URL || "/api";

export default function DatabloomPanel() {
  const [files, setFiles] = useState([]);
  const [source, setSource] = useState("");
  const [chunks, setChunks] = useState([]);
  const [summaries, setSummaries] = useState({}); // chunk_id -> markdown
  const [loadingId, setLoadingId] = useState(null);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/databloom/files`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => setFiles(d.files || []))
      .catch(() => setError("Could not reach the backend. Is uvicorn running on :8000?"));
  }, []);

  useEffect(() => {
    if (!source) return;
    setChunks([]);
    setSummaries({});
    setError("");
    setLoadingChunks(true);
    fetch(`${API}/databloom/chunks?source=${encodeURIComponent(source)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => setChunks(d.chunks))
      .catch(() => setError("Could not load chunks for this file."))
      .finally(() => setLoadingChunks(false));
  }, [source]);

  async function summarize(chunkId) {
    setLoadingId(chunkId);
    setError("");
    try {
      const r = await fetch(`${API}/databloom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, chunk_id: chunkId }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${r.status})`);
      }
      const d = await r.json();
      setSummaries((s) => ({ ...s, [chunkId]: d.summary }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg p-6 space-y-5">
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">Summarize a document</h2>
        <p className="text-sm text-slate-500">
          Pick an ingested file, then summarize any chunk into headings, bullets and a key point.
        </p>
      </div>

      <select
        className="w-full rounded-xl border border-slate-200 bg-stone-50 px-4 py-3 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-800"
        value={source}
        onChange={(e) => setSource(e.target.value)}
      >
        <option value="">
          {files.length ? "Choose a file…" : "No files yet. Upload one on the Contribute page."}
        </option>
        {files.map((f) => (
          <option key={f} value={f}>{f}</option>
        ))}
      </select>

      {error && (
        <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>
      )}
      {loadingChunks && <p className="text-sm text-slate-500">Loading chunks…</p>}
      {chunks.length > 0 && (
        <p className="text-xs font-semibold uppercase tracking-wider text-amber-600">
          {chunks.length} chunks
        </p>
      )}

      <ul className="space-y-3">
        {chunks.map((c) => (
          <li key={c.chunk_id} className="rounded-xl border border-slate-200 p-4 space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="text-xs font-mono text-slate-400">Chunk {c.index + 1}</span>
                <p className="text-sm text-slate-700 break-words">{c.preview}…</p>
              </div>
              <button
                onClick={() => summarize(c.chunk_id)}
                disabled={loadingId === c.chunk_id}
                className="shrink-0 rounded-lg bg-blue-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loadingId === c.chunk_id
                  ? "Summarizing…"
                  : summaries[c.chunk_id] ? "Re-run" : "Summarize"}
              </button>
            </div>
            {summaries[c.chunk_id] && (
              <div className="prose prose-sm max-w-none rounded-lg bg-stone-50 p-4">
                <ReactMarkdown>{summaries[c.chunk_id]}</ReactMarkdown>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
