import { useEffect, useRef, useState } from 'react';
import { Eye, EyeOff, KeyRound } from 'lucide-react';
import { api, ApiError } from '@/api/client';
import type { ApiKeyStatus } from '@/api/types';
import { StatusBadge } from './StatusBadge';
import { cn } from '@/lib/cn';

export function ApiKeySettings() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ApiKeyStatus | null>(null);
  const [draft, setDraft] = useState('');
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  async function refresh() {
    try {
      const s = await api.getApiKeyStatus();
      setStatus(s);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    }
  }

  async function save() {
    const key = draft.trim();
    if (!key) return;
    setBusy(true);
    setError(null);
    try {
      const s = await api.setApiKey(key);
      setStatus(s);
      setDraft('');
      setReveal(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    setError(null);
    try {
      const s = await api.clearApiKey();
      setStatus(s);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const configured = status?.configured === true;

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        title="Anthropic API key"
        aria-label="Anthropic API key settings"
        aria-expanded={open}
        className={cn(
          'inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium',
          configured
            ? 'text-ok-700 hover:bg-ok-50 dark:text-ok-500 dark:hover:bg-ok-500/10'
            : 'text-warn-700 hover:bg-warn-50 dark:text-warn-500 dark:hover:bg-warn-500/10',
        )}
      >
        <KeyRound size={14} />
        <span>API key</span>
        <span
          aria-hidden
          className={cn(
            'inline-block h-1.5 w-1.5 rounded-full',
            configured ? 'bg-ok-500' : 'bg-warn-500',
          )}
        />
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Anthropic API key"
          className="absolute right-0 z-20 mt-2 w-80 rounded-card border border-ink-200 bg-white p-4 shadow-lg dark:border-ink-700 dark:bg-ink-800"
        >
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900 dark:text-ink-50">Anthropic API key</h2>
            <StatusBadge tone={configured ? 'ok' : 'warn'}>
              {configured ? 'Configured' : 'Not set'}
            </StatusBadge>
          </div>
          <p className="mb-3 text-xs text-ink-500 dark:text-ink-400">
            Used by the prose extractor. Stored on the backend only — never sent back to this page.
          </p>

          {status?.masked && (
            <div className="mb-3 rounded-md border border-ink-200 bg-ink-50 px-2 py-1.5 font-mono text-[11px] text-ink-700 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-200">
              {status.masked}
            </div>
          )}

          <label className="mb-1 block text-[11px] font-medium text-ink-600 dark:text-ink-300">
            {configured ? 'Replace with a new key' : 'Paste your key'}
          </label>
          <div className="relative">
            <input
              type={reveal ? 'text' : 'password'}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder="sk-ant-..."
              autoComplete="off"
              spellCheck={false}
              className="w-full rounded-md border border-ink-300 bg-white px-2 py-1.5 pr-8 font-mono text-xs text-ink-900 outline-none focus:border-brand-500 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
            />
            <button
              type="button"
              onClick={() => setReveal(v => !v)}
              tabIndex={-1}
              aria-label={reveal ? 'Hide key' : 'Show key'}
              className="absolute right-1 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-700"
            >
              {reveal ? <EyeOff size={12} /> : <Eye size={12} />}
            </button>
          </div>

          {error && (
            <div className="mt-2 rounded-md border border-danger-500/40 bg-danger-50 px-2 py-1.5 text-[11px] text-danger-700 dark:bg-danger-500/10 dark:text-danger-500">
              {error}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={clear}
              disabled={busy || !configured}
              className="text-[11px] font-medium text-ink-500 hover:text-danger-700 disabled:cursor-not-allowed disabled:opacity-40 dark:text-ink-400 dark:hover:text-danger-500"
            >
              Clear saved key
            </button>
            <button
              type="button"
              onClick={save}
              disabled={busy || draft.trim().length === 0}
              className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Save key'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
