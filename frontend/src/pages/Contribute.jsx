import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../AuthContext";

/* ---------- Icons (inline, no extra packages) ---------- */
const UploadIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 16V4" /><path d="M6 10l6-6 6 6" /><path d="M4 20h16" />
  </svg>
);
const CodeIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 6l-6 6 6 6" /><path d="M16 6l6 6-6 6" />
  </svg>
);
const LinkIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1.5 1.5" />
    <path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1.5-1.5" />
  </svg>
);

const TABS = [
  { id: "file", label: "Upload file", Icon: UploadIcon },
  { id: "repo", label: "GitHub repo", Icon: CodeIcon },
  { id: "wiki", label: "Wiki URL", Icon: LinkIcon },
];

const STEPS = ["Queued", "Parsed & chunked", "Embedded", "Searchable"];

// Which progress step is lit for each job status
function activeStep(status) {
  if (status === "queued") return 1;
  if (status === "processing") return 3;
  if (status === "done") return 4;
  return 0;
}

const STATUS_BADGE = {
  queued: "bg-gray-100 text-gray-700",
  processing: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function Contribute() {
  const [tab, setTab] = useState("file");
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [currentJob, setCurrentJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const fileInputRef = useRef(null);

  // Logged-in user (for the department shown on the page)
  const { user } = useAuth();

  // Recent jobs list, refreshed every 3 seconds
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await api("/contribute/jobs");
        if (!alive) return;
        setJobs(data);
        if (currentJob) {
          const updated = data.find((j) => j.job_id === currentJob.job_id);
          if (updated) setCurrentJob(updated);
        }
      } catch {
        /* ignore, will retry */
      }
    }
    load();
    const id = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [currentJob?.job_id]);

  function pickFile(f) {
    if (f) {
      setFile(f);
      setError("");
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    const fd = new FormData();
    fd.append("type", tab);
    if (tab === "file") {
      if (!file) return setError("Please choose a file first.");
      fd.append("file", file);
    } else {
      if (!url.trim()) return setError("Please enter a URL.");
      fd.append("url", url.trim());
    }

    setSubmitting(true);
    try {
      // api() adds the login token; the browser sets Content-Type for FormData
      const data = await api("/contribute", { method: "POST", body: fd });
      setCurrentJob(data);
      setJobs((prev) => [data, ...prev]);
      setFile(null);
      setUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(err.message || "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  const step = activeStep(currentJob?.status);

  return (
    <div className="min-h-screen bg-[#f3f2ee]">
      {/* Top band with progress steps */}
      <div className="bg-gradient-to-r from-[#0f1a4a] to-[#1f4596] pt-8 pb-40 px-6">
        <div className="max-w-5xl mx-auto flex items-center flex-wrap gap-y-3">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const lit = n <= step;
            return (
              <div key={label} className="flex items-center">
                <div
                  className={`flex items-center gap-3 rounded-full border px-5 py-2.5 text-sm font-medium transition ${
                    lit ? "bg-white text-[#0f1a4a] border-white" : "border-white/60 text-white"
                  }`}
                >
                  <span>{n}</span>
                  <span>{label}</span>
                </div>
                {n < STEPS.length && <div className="w-8 h-px bg-white/40 mx-1" />}
              </div>
            );
          })}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 -mt-32 pb-16">
        {/* Main card */}
        <form onSubmit={handleSubmit} className="bg-white border border-black rounded-2xl p-8">
          {/* Tabs */}
          <div className="flex justify-center gap-10 mb-8">
            {TABS.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setTab(id);
                  setError("");
                }}
                className={`flex items-center gap-2 pb-2 font-medium border-b-2 transition ${
                  tab === id
                    ? "text-black border-black"
                    : "text-gray-500 border-transparent hover:text-black"
                }`}
              >
                <Icon className="w-4 h-4" />
                {label}
              </button>
            ))}
          </div>

          {/* Input area */}
          {tab === "file" ? (
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pickFile(e.dataTransfer.files[0]);
              }}
              className={`border border-dashed rounded-xl py-14 flex flex-col items-center gap-3 cursor-pointer transition ${
                dragging ? "border-black bg-gray-50" : "border-gray-300"
              }`}
            >
              <UploadIcon className="w-6 h-6" />
              <p className="font-mono text-sm">
                {file ? file.name : "Click to choose or drag a file here"}
              </p>
              <p className="text-sm text-gray-600">PDF, DOCX, TXT or Markdown</p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.md"
                className="hidden"
                onChange={(e) => pickFile(e.target.files[0])}
              />
            </div>
          ) : (
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={
                tab === "repo" ? "https://github.com/user/repo" : "https://example.com/wiki/page"
              }
              className="w-full border border-gray-300 rounded-xl px-4 py-4 text-sm focus:outline-none focus:border-black"
            />
          )}

          <hr className="my-6 border-black" />

          {/* Department (read-only, from login) + Submit */}
          <div className="flex flex-col sm:flex-row sm:items-end gap-4">
            <div className="flex-1">
              <p className="font-medium mb-2">Department</p>
              <div className="border border-black rounded-xl px-5 py-3 font-semibold bg-gray-50">
                {user?.department || "—"}
              </div>
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="bg-[#0f1a4a] hover:bg-[#1f4596] text-white font-medium rounded-xl px-8 py-3 transition disabled:opacity-50"
            >
              {submitting ? "Submitting…" : "Submit"}
            </button>
          </div>

          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
        </form>

        {/* Ingestion list */}
        <div className="flex items-end justify-between mt-10 mb-3">
          <h2 className="text-2xl font-semibold">Ingestion</h2>
          <span className="text-sm text-gray-600">Status refreshes automatically</span>
        </div>
        <div className="bg-white border border-black rounded-2xl divide-y">
          {jobs.length === 0 ? (
            <p className="p-6 text-sm text-gray-500">No contributions yet.</p>
          ) : (
            jobs.map((j) => (
              <div key={j.job_id} className="flex items-center justify-between gap-4 px-6 py-4">
                <div className="min-w-0">
                  <p className="font-mono text-sm truncate">
                    {j.type === "file" ? j.source.split(/[\\/]/).pop().replace(/^[\w-]{36}_/, "") : j.source}
                  </p>
                  <p className="text-xs text-gray-500">
                    {j.type}
                    {j.status === "done" && ` · ${j.chunks_added} chunks`}
                    {j.status === "failed" && j.error && ` · ${j.error}`}
                  </p>
                </div>
                <span
                  className={`shrink-0 text-xs px-2.5 py-1 rounded-full ${
                    STATUS_BADGE[j.status] || STATUS_BADGE.queued
                  }`}
                >
                  {j.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
