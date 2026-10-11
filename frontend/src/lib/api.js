// Every backend call lives in this file. If your FastAPI request/response
// field names differ, change them here and nothing else needs to move.

import { api as authFetch } from '../api';

// Every request goes through src/api.js, which adds the login token and
// refreshes it when it expires. Same signature as before, so callers don't change.
function request(path, { method = 'GET', body, form } = {}) {
  return authFetch(path, { method, body: form ?? body });
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
    form.append('type', kind); // backend field is "type": "file" | "repo" | "wiki"
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
    const data = await request('/databloom/files'); // -> { files: ["a.pdf", ...] }
    return (data.files ?? []).map((name) => ({ name }));
  },
  // -> { source, count, chunks: [{ chunk_id, index, preview, length, summarized }] }
  chunks: (fileName) => request(`/databloom/chunks?source=${encodeURIComponent(fileName)}`),
  summarize: async (fileName, chunkId) => {
    const res = await request('/databloom', { method: 'POST', body: { source: fileName, chunk_id: chunkId } });
    return res.summary ?? '';
  },

  // ---------- Feed ----------
  feed: (sort) => request(sort === 'trending' ? '/feed/trending' : '/feed'),
  // value: 1, -1, or 0 to remove your vote
  // You vote as the logged-in user; the backend reads who you are from the login.
  vote: (postId, value) => request(`/posts/${postId}/vote`, { method: 'POST', body: { value } }),
  createPost: (post) => request('/posts', { method: 'POST', body: post }),
  subscriptions: (email) => request(`/subscriptions?email=${encodeURIComponent(email)}`), // -> ["engineering", ...]
  subscribe: (tag, email) => request('/subscriptions', { method: 'POST', body: { tag, email } }),
  unsubscribe: (tag, email) =>
    request(`/subscriptions?tag=${encodeURIComponent(tag)}&email=${encodeURIComponent(email)}`, { method: 'DELETE' }),
};
