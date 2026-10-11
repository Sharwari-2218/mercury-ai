import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Shell, { card } from '../components/Shell';
import Segmented from '../components/Segmented';
import AnswerCard from '../components/AnswerCard';
import { ArrowUpIcon, ChevronDownIcon } from '../components/Icons';
import { api, normalizeSource } from '../lib/api';
import { MODES, modeOf } from '../lib/modes';
import { useAuth } from '../AuthContext';

const chip =
  'min-h-11 cursor-pointer rounded-full border border-line-strong bg-white px-4 text-sm text-ink hover:border-teal hover:text-teal';

function ScopePicker({ mode, scopes, scope, setScope }) {
  if (!mode.needsScope) {
    return <span className="text-[13px] text-mist">{mode.scopeText}</span>;
  }
  const control =
    'min-h-11 rounded-[9px] border border-panel-line bg-panel/70 font-mono text-[13px] text-white outline-none focus:border-amber';
  return (
    <label className="flex items-center gap-3">
      <span className="text-[13px] text-mist">{mode.scopeLabel}</span>
      {scopes.length ? (
        <span className="relative">
          <select value={scope} onChange={(e) => setScope(e.target.value)} className={`${control} appearance-none pl-3.5 pr-9`}>
            {scopes.map((s) => (
              <option key={s.value} value={s.value} className="text-ink">{s.label}</option>
            ))}
          </select>
          <ChevronDownIcon size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-white" />
        </span>
      ) : (
        <input
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          placeholder={mode.scopePlaceholder}
          className={`${control} w-80 max-w-full px-3.5 placeholder:text-mist/70`}
        />
      )}
    </label>
  );
}

export default function Ask() {
  const { can } = useAuth();
  // Only the modes this user's department may use ("All" is always there).
  const modes = MODES.filter((m) => !m.needs || can(m.needs));
  const [chosenMode, setModeValue] = useState('gittalk');
  const modeValue = modes.some((m) => m.value === chosenMode) ? chosenMode : modes[0].value;
  const [scopes, setScopes] = useState([]);
  const [scope, setScope] = useState('');
  const [turns, setTurns] = useState([]);
  const [draft, setDraft] = useState('');
  const inputRef = useRef(null);
  const endRef = useRef(null);
  const [params, setParams] = useSearchParams();
  const mode = modeOf(modeValue);
  const busy = turns.at(-1)?.status === 'loading';
  const lastDone = [...turns].reverse().find((t) => t.status === 'done');

  // Ctrl K / Search button land here with ?focus=1
  useEffect(() => {
    if (params.get('focus')) {
      inputRef.current?.focus();
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  // Load repos / documents for the scope picker when the mode changes.
  useEffect(() => {
    let alive = true;
    setScope('');
    setScopes([]);
    api.listScopes(modeValue).then((list) => {
      if (!alive) return;
      setScopes(list);
      setScope(list[0]?.value ?? '');
    });
    return () => { alive = false; };
  }, [modeValue]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length]);

  async function ask(text) {
    const question = text.trim();
    if (!question || busy) return;
    const id = crypto.randomUUID();
    if (mode.needsScope && !scope.trim()) {
      setTurns((t) => [...t, { id, question, mode: modeValue, scope: '', status: 'error', error: `Pick a ${mode.scopeLabel.toLowerCase()} above first.` }]);
      return;
    }
    const scopeLabel = scopes.find((s) => s.value === scope)?.label ?? scope;
    setTurns((t) => [...t, { id, question, mode: modeValue, scope: mode.needsScope ? scopeLabel : '', status: 'loading' }]);
    setDraft('');
    try {
      const res = await api.ask(modeValue, question, scope);
      setTurns((t) =>
        t.map((x) =>
          x.id === id
            ? {
                ...x,
                status: 'done',
                answer: res.answer ?? '',
                sources: (res.sources ?? []).map(normalizeSource),
                suggestions: res.suggestions ?? [],
              }
            : x,
        ),
      );
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, status: 'error', error: e.message } : x)));
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ask(draft);
    }
  }

  return (
    <Shell
      eyebrow="Company knowledge assistant"
      title="Ask your company anything"
      description="Answers come only from indexed docs, code and wikis, and every answer cites its sources."
      headerExtra={
        <>
          <div className="mt-2">
            <Segmented
              label="Search mode"
              options={modes.map((m) => ({ value: m.value, label: m.label }))}
              value={modeValue}
              onChange={setModeValue}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <ScopePicker mode={mode} scopes={scopes} scope={scope} setScope={setScope} />
            <span className="text-[13px] text-mist">{mode.hint}</span>
          </div>
        </>
      }
    >
      <div className={`${card} flex max-w-[920px] flex-col gap-6 p-5 sm:p-7`}>
        <section aria-label="Conversation" aria-live="polite" className="flex flex-col gap-5">
          {turns.length === 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="text-lg font-bold tracking-tight">Try asking</h2>
              <div className="flex flex-wrap gap-2">
                {mode.examples.map((q) => (
                  <button key={q} type="button" className={chip} onClick={() => ask(q)}>{q}</button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn) => (
            <div key={turn.id} className="flex flex-col gap-5">
              <div className="max-w-[80%] self-end rounded-[16px_16px_4px_16px] bg-ombre-soft px-4 py-3 text-[15px] leading-normal text-white">
                {turn.question}
              </div>
              <AnswerCard turn={turn} />
            </div>
          ))}

          {lastDone?.suggestions?.length > 0 && !busy && (
            <div className="flex flex-col gap-2.5">
              <h2 className="text-xs font-bold uppercase tracking-[0.08em] text-muted">Follow-up questions</h2>
              <div className="flex flex-wrap gap-2">
                {lastDone.suggestions.map((s) => (
                  <button key={s} type="button" className={chip} onClick={() => ask(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </section>

        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            ask(draft);
          }}
        >
          <div className="flex items-end gap-2.5 rounded-[14px] border border-line-strong bg-cream py-2.5 pl-4 pr-2.5 focus-within:border-teal">
            <textarea
              ref={inputRef}
              aria-label="Your question"
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={mode.placeholder}
              className="min-w-0 flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-normal text-ink outline-none placeholder:text-muted"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={busy || !draft.trim()}
              className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-[10px] bg-ombre-soft text-amber disabled:cursor-default disabled:opacity-50"
            >
              <ArrowUpIcon strokeWidth={2.2} />
            </button>
          </div>
          <p className="text-xs text-muted">
            Enter to send, Shift + Enter for a new line. If the answer isn't in the indexed sources, Mercury says so instead of guessing.
          </p>
        </form>
      </div>
    </Shell>
  );
}
