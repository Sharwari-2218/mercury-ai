import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { api } from '../lib/api';
import { modeOf } from '../lib/modes';
import { useAuth } from '../AuthContext';
import { ArrowDownIcon, ArrowUpIcon, CheckIcon, ListIcon, Logo } from './Icons';

const sectionLabel = 'text-xs font-bold uppercase tracking-[0.08em] text-muted';

function Header({ turn }) {
  const mode = modeOf(turn.mode);
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <Logo size={26} ring="var(--color-teal)" planet="var(--color-navy-900)" />
      <span className="text-sm font-bold">Mercury</span>
      <span className="rounded-full bg-chip px-2.5 py-0.5 font-mono text-xs text-body">
        {mode.label}
        {turn.scope ? ` · ${turn.scope}` : ''}
      </span>
    </div>
  );
}

export default function AnswerCard({ turn }) {
  const { user } = useAuth();
  const [copied, setCopied] = useState(false);
  const [posted, setPosted] = useState('idle'); // idle | saving | done | error
  const [rating, setRating] = useState(0);

  if (turn.status === 'loading') {
    return (
      <article className="flex flex-col gap-4" aria-busy="true">
        <Header turn={turn} />
        <p className="text-sm text-muted">Searching keywords and vectors, then fusing the results…</p>
        <div className="flex animate-pulse flex-col gap-2.5">
          <div className="h-3.5 w-11/12 rounded bg-chip" />
          <div className="h-3.5 w-4/5 rounded bg-chip" />
          <div className="h-3.5 w-3/5 rounded bg-chip" />
        </div>
      </article>
    );
  }

  if (turn.status === 'error') {
    return (
      <div role="alert" className="rounded-xl bg-err-bg px-4 py-3 text-sm text-err">
        Couldn't get an answer: {turn.error}
      </div>
    );
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(turn.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  }

  async function postToFeed() {
    setPosted('saving');
    try {
      await api.createPost({
        question: turn.question,
        answer: turn.answer,
        official_tag: turn.mode,
        dept_tag: user?.department?.toLowerCase() ?? null,
        user_email: user?.email ?? null,
        user_name: user?.name ?? null,
      });
      setPosted('done');
    } catch {
      setPosted('error');
    }
  }

  return (
    <article className="flex flex-col gap-[18px]">
      <Header turn={turn} />

      <details className="rounded-xl border border-line bg-cream px-4 py-3">
        <summary className="cursor-pointer text-[13px] font-semibold text-body">How this was found: 3-layer search</summary>
        <ol className="mt-2.5 flex list-decimal flex-col gap-1.5 pl-5 text-[13px] leading-normal text-body">
          <li>Query rewritten into alternative phrasings by the LLM</li>
          <li>Keyword layer: BM25 over stored chunks, top 10</li>
          <li>Vector layer: Chroma similarity search, top 10</li>
          <li>Merged with Reciprocal Rank Fusion, top 5 sent to the model</li>
        </ol>
      </details>

      <div className="markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer ?? ''}</ReactMarkdown>
      </div>

      <div className="flex flex-col gap-2">
        <h2 className={sectionLabel}>Sources</h2>
        {turn.sources?.length ? (
          <div className="flex flex-wrap gap-2">
            {turn.sources.map((s, i) => (
              <div key={`${s.path}-${i}`} className="flex min-h-12 flex-[1_1_240px] items-center gap-2.5 rounded-[10px] border border-line bg-cream px-3.5">
                <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md bg-teal text-xs font-bold text-white">
                  {i + 1}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="break-all font-mono text-[13px]">{s.path}</span>
                  {(s.type || s.chunk != null) && (
                    <span className="text-xs text-muted">
                      {[s.type, s.chunk != null ? `chunk ${s.chunk}` : null].filter(Boolean).join(' · ')}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No sources came back for this answer.</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-chip pt-3.5">
        <button
          type="button"
          onClick={postToFeed}
          disabled={posted === 'saving' || posted === 'done'}
          className="flex min-h-11 cursor-pointer items-center gap-2 rounded-[10px] bg-teal px-[18px] text-sm font-semibold text-white hover:bg-teal-dark disabled:cursor-default disabled:opacity-80"
        >
          {posted === 'done' ? <CheckIcon size={16} strokeWidth={2.4} /> : <ListIcon size={16} />}
          {posted === 'done' ? 'Posted to Feed' : posted === 'saving' ? 'Posting…' : 'Post to Feed'}
        </button>
        <button
          type="button"
          onClick={copy}
          className="min-h-11 cursor-pointer rounded-[10px] border border-line-strong bg-white px-4 text-sm font-medium text-body hover:text-ink"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        {posted === 'error' && <span className="text-sm text-err">Couldn't post. Try again.</span>}
        <div className="ml-auto flex gap-1">
          <button
            type="button"
            aria-label="Helpful"
            aria-pressed={rating === 1}
            onClick={() => setRating(rating === 1 ? 0 : 1)}
            className={`flex h-11 w-11 cursor-pointer items-center justify-center rounded-[10px] hover:bg-chip ${rating === 1 ? 'text-teal' : 'text-muted'}`}
          >
            <ArrowUpIcon />
          </button>
          <button
            type="button"
            aria-label="Not helpful"
            aria-pressed={rating === -1}
            onClick={() => setRating(rating === -1 ? 0 : -1)}
            className={`flex h-11 w-11 cursor-pointer items-center justify-center rounded-[10px] hover:bg-chip ${rating === -1 ? 'text-err' : 'text-muted'}`}
          >
            <ArrowDownIcon />
          </button>
        </div>
      </div>
    </article>
  );
}
