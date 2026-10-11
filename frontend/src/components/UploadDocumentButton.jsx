import { useRef, useState } from 'react';
import { api } from '../lib/api';
import { UploadIcon } from './Icons';

const ACCEPT = '.pdf,.docx,.txt,.md';
const MAX_BYTES = 20 * 1024 * 1024; // same limit as the backend

// A button that opens the file chooser, uploads the file to /docsense/upload and
// calls onUploaded({ doc_id, filename, chunks }) when the backend has finished
// reading it. The document lands in the uploader's own department.
//
// tone="dark" for the navy band, "light" for white cards.
export default function UploadDocumentButton({ onUploaded, tone = 'light', label = 'Upload document' }) {
  const inputRef = useRef(null);
  const [state, setState] = useState({ status: 'idle', message: '' }); // idle | uploading | done | error

  async function handleFile(file) {
    if (!file) return;
    // Quick checks in the browser so people don't wait for an upload that will fail.
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPT.split(',').includes(ext)) {
      setState({ status: 'error', message: 'Only PDF, DOCX, TXT or Markdown files.' });
      return;
    }
    if (file.size > MAX_BYTES) {
      setState({ status: 'error', message: 'That file is over 20 MB.' });
      return;
    }

    setState({ status: 'uploading', message: `Reading ${file.name}…` });
    try {
      const doc = await api.uploadDocument(file);
      setState({ status: 'done', message: `Added ${doc.filename} (${doc.chunks} chunks).` });
      onUploaded?.(doc);
    } catch (e) {
      setState({ status: 'error', message: e.message || 'Upload failed.' });
    } finally {
      if (inputRef.current) inputRef.current.value = ''; // lets you pick the same file again
    }
  }

  const button =
    tone === 'dark'
      ? 'border border-panel-line bg-panel/70 text-white hover:border-amber'
      : 'border border-line-strong bg-white text-ink hover:border-teal hover:text-teal';
  const note = {
    uploading: tone === 'dark' ? 'text-mist' : 'text-muted',
    done: tone === 'dark' ? 'text-[#9fe0b7]' : 'text-ok',
    error: tone === 'dark' ? 'text-[#ffb4a8]' : 'text-err',
  }[state.status];

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={state.status === 'uploading'}
        className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-[9px] px-4 text-sm font-semibold transition-colors disabled:cursor-wait disabled:opacity-60 ${button}`}
      >
        <UploadIcon size={16} />
        {state.status === 'uploading' ? 'Uploading…' : label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
      {state.message && (
        <span role={state.status === 'error' ? 'alert' : 'status'} className={`text-[13px] ${note}`}>
          {state.message}
        </span>
      )}
    </div>
  );
}
