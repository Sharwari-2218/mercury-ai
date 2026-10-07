// Every backend call lives in this file. If your FastAPI request/response
// field names differ, change them here and nothing else needs to move.

const BASE = import.meta.env.VITE_API_URL ?? '/api';

async function request(path, { method = 'GET', body, form } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: form ?? (body ? JSON.stringify(body) : undefined),
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (data?.detail) message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* body wasn't JSON */ }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

// ---------- Ask ----------
// One entry per mode on the Ask page: which endpoint it calls and the JSON body it sends.
const ASK = {
  all: { path: '/ask', body: (question) => ({ question }) },
  gittalk: { path: '/gittalk/ask', body: (question, scope) => ({ question, repo_url: scope }) },
  docsense: { path: '/docsense/ask', body: (question, scope) => ({ question, file: scope }) },
  sharebase: { path: '/sharebase/ask', body: (question) => ({ question }) },
};

// Lists for the scope picker. Return [] if the endpoint doesn't exist yet;
// the UI then falls back to a text box.
const SCOPES = {
  gittalk: '/gittalk/repos',   // -> ["https://github.com/o/r", ...] or [{ name, repo_url }, ...]
  docsense: '/docsense/files', // -> ["handbook.pdf", ...]
};

// Sources can come back as strings or objects; this turns either into one shape.
export function normalizeSource(s) {
  if (typeof s === 'string') return { path: s };
  return {
    path: s.source ?? s.path ?? s.file ?? 'source',
    type: s.type ?? null,
    chunk: s.chunk ?? s.chunk_id ?? s.page ?? null,
  };
}

const shortRepo = (s) => String(s).replace(/^https?:\/\/(www\.)?github\.com\//, '').replace(/\.git$/, '');

// Turns a scope entry (a string, or an object like { name, repo_url }) into
// { value: what gets sent to the API, label: what the picker shows }.
function asOption(x) {
  if (typeof x === 'string') return { value: x, label: shortRepo(x) };
  const value = x.repo_url ?? x.url ?? x.file ?? x.filename ?? x.name ?? x.collection ?? x.collection_name ?? x.id;
  const label = x.name ?? x.repo_name ?? x.filename ?? x.collection ?? x.collection_name ?? value;
  return { value: value == null ? '' : String(value), label: shortRepo(label ?? '') };
}

export const api = {
  ask: (mode, question, scope) =>
    request(ASK[mode].path, { method: 'POST', body: ASK[mode].body(question, scope) }),

  listScopes: async (mode) => {
    if (!SCOPES[mode]) return [];
    try {
      const data = await request(SCOPES[mode]);
      const list = Array.isArray(data) ? data : data.repos ?? data.files ?? data.items ?? [];
      return list.map(asOption).filter((o) => o.value);
    } catch {
      return [];
    }
  },

  // ---------- Contribute ----------
  // POST /contribute (multipart) -> { job_id, status }
  contribute: ({ kind, file, url, branch, department, uploadedBy }) => {
    const form = new FormData();
    form.append('kind', kind); // "file" | "repo" | "wiki"
    if (file) form.append('file', file);
    if (url) form.append('url', url);
    if (branch) form.append('branch', branch);
    form.append('department', department);
    form.append('uploaded_by', uploadedBy);
    return request('/contribute', { method: 'POST', form });
  },
  // GET /contribute/status/{id} -> { status: queued|started|finished|failed, step?, error? }
  jobStatus: (id) => request(`/contribute/status/${encodeURIComponent(id)}`),

  // ---------- Databloom ----------
  databloomFiles: async () => {
    const list = await request('/databloom/files'); // -> [{ name, type, department }] or ["a.pdf"]
    return list.map((f) => (typeof f === 'string' ? { name: f } : f));
  },
  chunks: (fileName) => request(`/databloom/files/${encodeURIComponent(fileName)}/chunks`), // -> [{ id, text, page? }]
  summarize: async (fileName, chunkId) => {
    const res = await request('/databloom', { method: 'POST', body: { file: fileName, chunk_id: chunkId } });
    return typeof res === 'string' ? res : res.summary ?? res.markdown ?? '';
  },

  // ---------- Feed ----------
  feed: (sort) => request(sort === 'trending' ? '/feed/trending' : '/feed'),
  // value: 1, -1, or 0 to remove your vote
  vote: (postId, value, userEmail) =>
    request(`/posts/${postId}/vote`, { method: 'POST', body: { value, user_email: userEmail } }),
  createPost: (post) => request('/posts', { method: 'POST', body: post }),
  subscriptions: (email) => request(`/subscriptions?email=${encodeURIComponent(email)}`), // -> ["engineering", ...]
  subscribe: (tag, email) => request('/subscriptions', { method: 'POST', body: { tag, email } }),
  unsubscribe: (tag, email) =>
    request(`/subscriptions?tag=${encodeURIComponent(tag)}&email=${encodeURIComponent(email)}`, { method: 'DELETE' }),
};
