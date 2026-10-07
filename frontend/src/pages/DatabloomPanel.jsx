// Place at: frontend/src/components/DatabloomPanel.jsx
// Rendered inside the main Chat page when mode === "databloom".
// Requires: npm install react-markdown
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

const API = import.meta.env.VITE_API_URL || "/api";

export default function DatabloomPanel() {
  const [files, setFiles] = useState([]);
  const [source, setSource] = useState("");
  const [chunks, setChunks] = useState([]);
  const [summaries, setSummaries] = useState({}); // chunk_id -> markdown
  const [loadingId, setLoadingId] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/databloom/files`)
      .then((r) => r.json())
      .then((d) => setFiles(d.files || []))
      .catch(() => setError("Could not reach the backend."));
  }, []);

  useEffect(() => {
    if (!source) return;
    setChunks([]);
    setSummaries({});
    setError("");
    fetch(`${API}/databloom/chunks?source=${encodeURIComponent(source)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => setChunks(d.chunks))
      .catch(() => setError("Could not load chunks for this file."));
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
      if (!r.ok) throw new Error((await r.json()).detail || "Request failed");
      const d = await r.json();
      setSummaries((s) => ({ ...s, [chunkId]: d.summary }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingId(null);
    }
  }

  return (
    <div className="space-y-4">
      <select
        className="border rounded p-2 w-full"
        value={source}
        onChange={(e) => setSource(e.target.value)}
      >
        <option value="">Choose a file to summarize…</option>
        {files.map((f) => (
          <option key={f} value={f}>{f}</option>
        ))}
      </select>

      {error && <p className="text-red-600">{error}</p>}
      {chunks.length > 0 && (
        <p className="text-sm text-gray-500">{chunks.length} chunks</p>
      )}

      <ul className="space-y-4">
        {chunks.map((c) => (
          <li key={c.chunk_id} className="border rounded-lg p-4 space-y-3">
            <div className="flex justify-between items-start gap-4">
              <div>
                <span className="text-xs font-mono text-gray-500">
                  Chunk {c.index + 1}
                </span>
                <p className="text-sm text-gray-700">{c.preview}…</p>
              </div>
              <button
                onClick={() => summarize(c.chunk_id)}
                disabled={loadingId === c.chunk_id}
                className="shrink-0 bg-blue-600 text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
              >
                {loadingId === c.chunk_id
                  ? "Summarizing…"
                  : summaries[c.chunk_id] ? "Re-run" : "Summarize"}
              </button>
            </div>
            {summaries[c.chunk_id] && (
              <div className="prose prose-sm max-w-none bg-gray-50 rounded p-3">
                <ReactMarkdown>{summaries[c.chunk_id]}</ReactMarkdown>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
