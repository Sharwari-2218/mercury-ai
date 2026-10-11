import { useEffect, useMemo, useState } from 'react';
import Shell, { card } from '../components/Shell';
import Segmented from '../components/Segmented';
import { CheckIcon, ChevronDownIcon, ChevronUpIcon } from '../components/Icons';
import { api } from '../lib/api';
import { timeAgo } from '../lib/format';
import { useAuth } from '../AuthContext';

const tagChip = 'rounded-full bg-chip px-2.5 py-0.5 font-mono text-xs text-body';

// Accepts the post shape from your API and fills in sensible defaults.
function normalizePost(p) {
  const score = p.score ?? (p.upvotes ?? 0) - (p.downvotes ?? 0);
  return {
    id: p.id,
    question: p.question,
    answer: p.answer ?? '',
    official: Boolean(p.official ?? p.is_official),
    tags: [p.dept_tag, p.official_tag].filter(Boolean),
    author: p.user_name ?? p.author ?? p.user?.name ?? 'Someone',
    createdAt: p.created_at,
    score,
  };
}

export default function Feed() {
  const { user } = useAuth();
  const [sort, setSort] = useState('trending');
  const [posts, setPosts] = useState(null);
  const [error, setError] = useState('');
  const [myVotes, setMyVotes] = useState({}); // post id -> 1 | -1 | 0, from the server
  const [subs, setSubs] = useState([]);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    setPosts(null);
    setError('');
    api.feed(sort)
      .then((list) => {
        setPosts(list.map(normalizePost));
        setMyVotes(Object.fromEntries(list.map((p) => [p.id, p.my_vote ?? 0])));
      })
      .catch((e) => { setPosts([]); setError(e.message); });
  }, [sort]);

  useEffect(() => {
    if (!user) return setSubs([]);
    api.subscriptions(user.email).then(setSubs).catch(() => {});
  }, [user]);

  const allTags = useMemo(() => {
    const set = new Set(subs);
    (posts ?? []).forEach((p) => p.tags.forEach((t) => set.add(t)));
    return [...set].slice(0, 10);
  }, [posts, subs]);

  async function vote(post, value) {
    const prev = myVotes[post.id] ?? 0;
    const next = prev === value ? 0 : value;
    const delta = next - prev;
    const apply = (d, v) => {
      setPosts((list) => list.map((p) => (p.id === post.id ? { ...p, score: p.score + d } : p)));
      setMyVotes((m) => ({ ...m, [post.id]: v }));
    };
    apply(delta, next); // optimistic
    try {
      await api.vote(post.id, next);
    } catch {
      apply(-delta, prev); // undo on failure
    }
  }

  async function toggleTag(tag) {
    if (!user) return;
    const following = subs.includes(tag);
    setSubs((s) => (following ? s.filter((t) => t !== tag) : [...s, tag]));
    try {
      if (following) await api.unsubscribe(tag, user.email);
      else await api.subscribe(tag, user.email);
    } catch {
      setSubs((s) => (following ? [...s, tag] : s.filter((t) => t !== tag)));
    }
  }

  return (
    <Shell
      eyebrow="Shared by your teammates"
      title="Feed"
      description="Answers people found useful enough to post. Vote up the ones that helped you."
      headerAside={
        <Segmented
          label="Sort posts"
          options={[{ value: 'trending', label: 'Trending' }, { value: 'newest', label: 'Newest' }]}
          value={sort}
          onChange={setSort}
        />
      }
    >
      <div className="flex flex-wrap items-start gap-6">
        <section aria-label="Posts" className="flex min-w-0 flex-[3_1_480px] flex-col gap-3">
          {error && <p role="alert" className="rounded-xl bg-err-bg px-4 py-3 text-sm text-err">{error}</p>}
          {posts === null && <div className={`${card} p-6 text-sm text-muted`}>Loading posts…</div>}
          {posts?.length === 0 && !error && (
            <div className={`${card} p-6 text-sm text-muted`}>No posts yet. Use “Post to Feed” under any answer on the Ask page.</div>
          )}

          {posts?.map((p) => {
            const mine = myVotes[p.id] ?? 0;
            const open = expanded[p.id];
            return (
              <article key={p.id} className="flex gap-4 rounded-[18px] border border-line bg-white py-5 pl-3 pr-[22px] shadow-[0_8px_24px_rgba(18,26,43,0.07)]">
                <div className="flex shrink-0 flex-col items-center self-start rounded-xl bg-paper py-0.5">
                  <button
                    type="button"
                    aria-label="Upvote"
                    aria-pressed={mine === 1}
                    onClick={() => vote(p, 1)}
                    className={`flex h-10 w-11 cursor-pointer items-center justify-center rounded-[10px] hover:bg-chip ${mine === 1 ? 'text-teal' : 'text-muted'}`}
                  >
                    <ChevronUpIcon size={20} strokeWidth={2.2} />
                  </button>
                  <span className="text-base font-bold">{p.score}</span>
                  <button
                    type="button"
                    aria-label="Downvote"
                    aria-pressed={mine === -1}
                    onClick={() => vote(p, -1)}
                    className={`flex h-10 w-11 cursor-pointer items-center justify-center rounded-[10px] hover:bg-chip ${mine === -1 ? 'text-err' : 'text-muted'}`}
                  >
                    <ChevronDownIcon size={20} strokeWidth={2.2} />
                  </button>
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    {p.official && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-ombre-soft px-2.5 py-0.5 text-xs font-bold text-amber">
                        <CheckIcon size={12} strokeWidth={2.5} />
                        Official
                      </span>
                    )}
                    {p.tags.map((t) => <span key={t} className={tagChip}>#{t}</span>)}
                  </div>
                  <h2 className="text-lg font-bold leading-snug tracking-tight">{p.question}</h2>
                  <p className={`whitespace-pre-line text-sm leading-relaxed text-body ${open ? '' : 'line-clamp-3'}`}>{p.answer}</p>
                  <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted">
                    <span>{p.author}{p.createdAt ? ` · ${timeAgo(p.createdAt)}` : ''}</span>
                    <button
                      type="button"
                      onClick={() => setExpanded((e) => ({ ...e, [p.id]: !open }))}
                      className="cursor-pointer font-semibold text-teal hover:text-teal-dark"
                    >
                      {open ? 'Show less' : 'Read full answer'}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </section>

        <aside aria-labelledby="subs-h" className={`${card} flex min-w-0 flex-[1_1_260px] flex-col overflow-hidden`}>
          <div className="flex flex-col gap-1.5 bg-ombre px-5 py-[18px]">
            <h2 id="subs-h" className="text-base font-bold text-white">Tag alerts</h2>
            <p className="text-[13px] leading-normal text-mist">Get an email when someone posts with a tag you follow.</p>
          </div>
          <div className="flex flex-col gap-2.5 px-5 pb-5 pt-4">
            {!user && <p className="text-sm text-muted">Sign in from your avatar in the top bar to follow tags.</p>}
            {user && allTags.length === 0 && <p className="text-sm text-muted">Tags from posts will appear here.</p>}
            {user &&
              allTags.map((tag) => {
                const following = subs.includes(tag);
                return (
                  <div key={tag} className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[13px]">#{tag}</span>
                    <button
                      type="button"
                      aria-pressed={following}
                      onClick={() => toggleTag(tag)}
                      className={`min-h-9 cursor-pointer rounded-lg px-3 text-[13px] font-semibold ${
                        following ? 'bg-teal text-white hover:bg-teal-dark' : 'border border-line-strong bg-white text-ink hover:border-teal'
                      }`}
                    >
                      {following ? 'Following' : 'Follow'}
                    </button>
                  </div>
                );
              })}
            <p className="mt-1.5 border-t border-chip pt-3 text-xs text-muted">
              {sort === 'trending' ? 'Trending ranks posts by votes, weighted toward newer ones.' : 'Showing newest posts first.'}
            </p>
          </div>
        </aside>
      </div>
    </Shell>
  );
}
