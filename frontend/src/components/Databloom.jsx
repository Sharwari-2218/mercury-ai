// Databloom: pick a document, see its chunks in order, and summarize any chunk.
//
// Backend calls (all need login + "doc" permission):
//   GET  /docsense/files               documents you can see (the picker)
//   GET  /databloom/{doc_id}/chunks    that document's chunks
//   POST /databloom                    { doc_id, chunk_id } -> { summary (markdown) }
import { useCallback, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Link, useSearchParams } from 'react-router-dom';
import Shell, { card } from './Shell';
import UploadDocumentButton from './UploadDocumentButton';
import { ChatIcon, ChevronDownIcon, FileIcon, SparkIcon } from './Icons';
import { api } from '../lib/api';

function DocumentPicker({ docs, docId, onChange }) {
  if (docs === null) return <span className="text-[13px] text-mist">Loading documents…</span>;
  if (docs.length === 0) return null;
  return (
    <label className="flex items-center gap-3">
      <span className="text-[13px] text-mist">Document</span>
      <span className="relative">
        <select
          value={docId}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-11 max-w-[min(420px,80vw)] appearance-none rounded-[9px] border border-panel-line bg-panel/70 pl-3.5 pr-9 font-mono text-[13px] text-white outline-none focus:border-amber"
        >
          {docs.map((d) => (
            <option key={d.doc_id} value={d.doc_id} className="text-ink">
              {d.filename}
            </option>
          ))}
        </select>
        <ChevronDownIcon size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-white" />
      </span>
    </label>
  );
}

function ChunkRow({ chunk, docId, result, onSummarize }) {
  const status = result?.status ?? 'idle'; // idle | loading | done | error
  const label = { loading: 'Summarizing…', done: 'Summarized' }[status] ?? 'Summarize';

  return (
    <li className="flex flex-col gap-3 border-b border-line px-5 py-5 last:border-b-0 sm:px-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-1.5">
          <span className="font-mono text-xs text-muted">
            Chunk {chunk.index + 1}
            {chunk.page != null && ` · page ${chunk.page + 1}`}
            {` · ${chunk.length.toLocaleString()} characters`}
          </span>
          <p className="text-[15px] leading-relaxed text-body">
            {chunk.preview}
            {chunk.length > chunk.preview.length && '…'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onSummarize(docId, chunk.chunk_id)}
          disabled={status === 'loading' || status === 'done'}
          className="flex min-h-11 shrink-0 cursor-pointer items-center gap-2 rounded-[10px] bg-teal px-4 text-sm font-semibold text-white hover:bg-teal-dark disabled:cursor-default disabled:opacity-70"
        >
          <SparkIcon size={16} />
          {label}
        </button>
      </div>

      {status === 'loading' && !result?.text && (
        <div className="flex animate-pulse flex-col gap-2 rounded-xl bg-cream p-4" aria-busy="true">
          <div className="h-3.5 w-2/5 rounded bg-chip" />
          <div className="h-3 w-11/12 rounded bg-chip" />
          <div className="h-3 w-4/5 rounded bg-chip" />
        </div>
      )}
      {result?.text && (
        <div className="markdown rounded-xl border border-line bg-cream px-5 py-4">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.text}</ReactMarkdown>
        </div>
      )}
      {status === 'error' && (
        <p role="alert" className="rounded-xl bg-err-bg px-4 py-3 text-sm text-err">
          Couldn't summarize this chunk: {result.error}
        </p>
      )}
    </li>
  );
}

export default function Databloom() {
  const [params, setParams] = useSearchParams();
  const docId = params.get('doc') ?? '';
  const setDocId = useCallback((id) => setParams(id ? { doc: id } : {}, { replace: true }), [setParams]);

  const [docs, setDocs] = useState(null);       // null = still loading
  const [docsError, setDocsError] = useState('');
  const [detail, setDetail] = useState(null);   // { filename, count, chunks, ... }
  const [chunksState, setChunksState] = useState('idle'); // idle | loading | error
  const [chunksError, setChunksError] = useState('');
  const [results, setResults] = useState({});   // chunk_id -> { status, text, error }

  // 1. The document list. `select` = choose this one afterwards (after an upload).
  const loadDocs = useCallback(
    async (select) => {
      setDocsError('');
      try {
        const list = await api.documents();
        setDocs(list);
        const wanted = select || docId;
        if (!list.some((d) => d.doc_id === wanted)) setDocId(list[0]?.doc_id ?? '');
        else if (select) setDocId(select);
      } catch (e) {
        setDocs([]);
        setDocsError(e.message);
      }
    },
    [docId, setDocId],
  );

  useEffect(() => {
    loadDocs();
    // Only on first load; later refreshes happen after an upload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. The chosen document's chunks.
  useEffect(() => {
    if (!docId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setChunksState('loading');
    setChunksError('');
    setResults({});
    api
      .chunks(docId)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setChunksState('idle');
      })
      .catch((e) => {
        if (!alive) return;
        setDetail(null);
        setChunksState('error');
        setChunksError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [docId]);

  // 3. Summarize one chunk. Several can run at once; each row tracks its own state.
  async function summarize(forDoc, chunkId) {
    setResults((r) => ({ ...r, [chunkId]: { ...r[chunkId], status: 'loading', error: '' } }));
    try {
      const res = await api.summarize(forDoc, chunkId);
      setResults((r) => ({ ...r, [chunkId]: { status: 'done', text: res.summary } }));
    } catch (e) {
      setResults((r) => ({ ...r, [chunkId]: { ...r[chunkId], status: 'error', error: e.message } }));
    }
  }

  const doc = docs?.find((d) => d.doc_id === docId);

  return (
    <Shell
      eyebrow="Databloom"
      title="Read a document one piece at a time"
      description="Mercury splits every document into chunks for search. Pick one and get a short summary of any chunk, using only that chunk's text."
      headerExtra={
        <div className="flex flex-wrap items-center gap-3">
          <DocumentPicker docs={docs} docId={docId} onChange={setDocId} />
          <UploadDocumentButton tone="dark" label="Upload" onUploaded={(d) => loadDocs(d.doc_id)} />
        </div>
      }
    >
      <div className={`${card} max-w-[920px] overflow-hidden`}>
        {docsError ? (
          <p role="alert" className="m-6 rounded-xl bg-err-bg px-4 py-3 text-sm text-err">
            Couldn't load your documents: {docsError}
          </p>
        ) : docs === null ? (
          <p className="p-7 text-sm text-muted">Loading documents…</p>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-start gap-4 p-7">
            <FileIcon size={28} className="text-muted" />
            <div className="flex flex-col gap-1">
              <h2 className="text-lg font-bold text-ink">No documents yet</h2>
              <p className="max-w-[520px] text-[15px] text-body">
                Upload a PDF, Word file, text or Markdown file. It's added for your department, and you can summarize it here or ask questions about it on the Ask page.
              </p>
            </div>
            <UploadDocumentButton onUploaded={(d) => loadDocs(d.doc_id)} label="Upload your first document" />
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line bg-cream px-5 py-4 sm:px-7">
              <div className="flex min-w-0 flex-col gap-0.5">
                <h2 className="break-all font-mono text-[15px] font-semibold text-ink">{doc?.filename ?? detail?.filename}</h2>
                <span className="text-[13px] text-muted">
                  {[
                    detail ? `${detail.count} chunks` : null,
                    doc?.department ? `${doc.department} department` : null,
                    doc?.uploaded_by ? `added by ${doc.uploaded_by}` : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </div>
              <Link
                to={`/?mode=docsense&doc=${encodeURIComponent(docId)}`}
                className="flex min-h-11 items-center gap-2 rounded-[10px] border border-line-strong bg-white px-4 text-sm font-semibold text-ink hover:border-teal hover:text-teal"
              >
                <ChatIcon size={16} />
                Ask about this document
              </Link>
            </header>

            {chunksState === 'loading' && (
              <div className="flex animate-pulse flex-col gap-3 p-7" aria-busy="true">
                <div className="h-3.5 w-1/4 rounded bg-chip" />
                <div className="h-3.5 w-11/12 rounded bg-chip" />
                <div className="h-3.5 w-4/5 rounded bg-chip" />
              </div>
            )}
            {chunksState === 'error' && (
              <p role="alert" className="m-6 rounded-xl bg-err-bg px-4 py-3 text-sm text-err">
                Couldn't load this document's chunks: {chunksError}
              </p>
            )}
            {chunksState === 'idle' && detail && (
              <ol aria-label="Chunks">
                {detail.chunks.map((c) => (
                  <ChunkRow key={c.chunk_id} chunk={c} docId={docId} result={results[c.chunk_id]} onSummarize={summarize} />
                ))}
              </ol>
            )}
          </>
        )}
      </div>
    </Shell>
  );
}