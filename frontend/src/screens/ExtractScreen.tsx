import { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Database, Loader2, RotateCcw, Send } from 'lucide-react';
import { api, ApiError, type ExtractStartOptions } from '@/api/client';
import type { ExtractState, ExtractTask, ExtractTaskStatus } from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { cn } from '@/lib/cn';

interface ExtractScreenProps {
  projectId: string;
  /** When true, the screen drives the backend with `dry_run=true`. */
  dryRun?: boolean;
  /** Dry-run only: name of a sheet whose first attempt should fail. */
  simulateFailureSheet?: string | null;
  /** Called when every task finishes and at least one succeeded. */
  onComplete?: (state: ExtractState) => void;
}

const POLL_MS = 500;
const TERMINAL: ExtractTaskStatus[] = ['done', 'failed'];

function isRunning(state: ExtractState | null): boolean {
  if (!state) return false;
  return state.tasks.some(t => t.status === 'queued' || t.status === 'running');
}

function isDone(state: ExtractState | null): boolean {
  if (!state || state.tasks.length === 0) return false;
  return state.tasks.every(t => TERMINAL.includes(t.status));
}

export function ExtractScreen({
  projectId,
  dryRun = false,
  simulateFailureSheet = null,
  onComplete,
}: ExtractScreenProps) {
  const [state, setState] = useState<ExtractState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const startedRef = useRef(false);
  const completedRef = useRef(false);

  const extractOpts: ExtractStartOptions = {
    dryRun,
    simulateFailureSheet: simulateFailureSheet ?? null,
  };

  // Kick off the run on mount. The backend POST is idempotent — a re-POST while
  // a run is in flight just returns the current state, so this is safe.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const next = await api.startExtract(projectId, extractOpts);
        setState(next);
      } catch (e) {
        // If a run already exists and the project is not at the EXTRACT stage,
        // the backend returns 409 — fall back to GET so we still show progress.
        if (e instanceof ApiError && e.status === 409) {
          try { setState(await api.getExtractState(projectId)); }
          catch (e2) { setError(e2 instanceof ApiError ? e2.detail : (e2 as Error).message); }
        } else {
          setError(e instanceof ApiError ? e.detail : (e as Error).message);
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Poll while anything is queued/running.
  useEffect(() => {
    if (!state || !isRunning(state)) return;
    const id = window.setInterval(async () => {
      try {
        const next = await api.getExtractState(projectId);
        setState(next);
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : (e as Error).message);
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [projectId, state]);

  // Fire onComplete once, when the run finishes with at least one success.
  useEffect(() => {
    if (!state || completedRef.current) return;
    if (!isDone(state)) return;
    const anyOk = state.tasks.some(t => t.status === 'done');
    if (anyOk) {
      completedRef.current = true;
      onComplete?.(state);
    }
  }, [state, onComplete]);

  async function retry(task: ExtractTask) {
    setRetrying(task.id);
    setError(null);
    try {
      // Drop simulateFailureSheet on retry — that knob is for the initial
      // demo path only. Without this, the dry-run extractor would re-fail
      // the same sheet because each request gets a fresh extractor instance
      // and its per-sheet attempt counter resets.
      const next = await api.retryExtractTask(projectId, task.id, { dryRun });
      setState(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setRetrying(null);
    }
  }

  const tables = state?.tasks.filter(t => t.kind === 'tables') ?? [];
  const prose = state?.tasks.filter(t => t.kind === 'prose_sheet') ?? [];
  const totalTasks = state?.tasks.length ?? 0;
  const doneTasks = state?.tasks.filter(t => TERMINAL.includes(t.status)).length ?? 0;
  const pct = totalTasks === 0 ? 0 : Math.round((doneTasks / totalTasks) * 100);

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900 dark:text-ink-50">Extract devices</h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          ProcessArc reads the structured tables locally, then sends each
          sequencing sheet's prose to the Claude API to identify devices. Watch
          the progress below — you can retry any failed step.
        </p>
        {dryRun && (
          <div className="mt-2 inline-block rounded-md border border-brand-500/40 bg-brand-50 px-2 py-1 text-[11px] font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-100">
            Dry-run mode — no Claude API call, no API key required.
          </div>
        )}
      </header>

      {error && (
        <div className="rounded-card border border-danger-500/40 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500">
          {error}
        </div>
      )}

      <BoundarySection
        icon={<Database size={14} />}
        title="Tables read directly"
        annotation="Local — never leaves your machine."
        tone="neutral"
      >
        {tables.length === 0 && state == null
          ? <RowSkeleton />
          : tables.map(t => (
              <TaskRow key={t.id} task={t} onRetry={retry} retrying={retrying === t.id} />
            ))}
      </BoundarySection>

      <BoundarySection
        icon={<Send size={14} />}
        title="Sent to Claude API"
        annotation="Sequence prose is sent — see Plan §8.3."
        tone="brand"
      >
        {prose.length === 0 && state == null
          ? <RowSkeleton />
          : prose.length === 0
            ? <Empty>No sequencing sheets to extract.</Empty>
            : prose.map(t => (
                <TaskRow key={t.id} task={t} onRetry={retry} retrying={retrying === t.id} />
              ))}
      </BoundarySection>

      <div className="rounded-card border border-ink-200 bg-white p-4 dark:border-ink-700 dark:bg-ink-800">
        <div className="mb-2 flex items-center justify-between text-xs text-ink-500 dark:text-ink-400">
          <span>Overall progress</span>
          <span>
            {doneTasks} / {totalTasks} · {state?.device_count ?? 0} devices found
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-700">
          <div
            className="h-full bg-brand-500 transition-all"
            style={{ width: `${pct}%` }}
            aria-label={`${pct}% complete`}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      </div>
    </section>
  );
}

function BoundarySection({
  icon, title, annotation, tone, children,
}: {
  icon: React.ReactNode;
  title: string;
  annotation: string;
  tone: 'neutral' | 'brand';
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800">
      <div className={cn(
        'flex items-center gap-2 border-b px-4 py-2 text-sm',
        tone === 'brand'
          ? 'border-brand-500/30 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-100 dark:border-brand-500/30'
          : 'border-ink-200 bg-ink-50 text-ink-700 dark:border-ink-700 dark:bg-ink-900 dark:text-ink-200',
      )}>
        <span aria-hidden>{icon}</span>
        <span className="font-medium">{title}</span>
        <span className="text-[11px] opacity-75">— {annotation}</span>
      </div>
      <ul className="divide-y divide-ink-100 dark:divide-ink-700">{children}</ul>
    </div>
  );
}

function TaskRow({
  task, onRetry, retrying,
}: {
  task: ExtractTask;
  onRetry: (t: ExtractTask) => void;
  retrying: boolean;
}) {
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StatusIcon status={task.status} />
          <span className="truncate text-sm text-ink-900 dark:text-ink-50">{task.label}</span>
        </div>
        {task.detail && (
          <div className={cn(
            'mt-0.5 truncate text-[11px]',
            task.status === 'failed'
              ? 'text-danger-700 dark:text-danger-500'
              : 'text-ink-500 dark:text-ink-400',
          )}>
            {task.detail}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <StatusBadgeForStatus status={task.status} />
        {task.status === 'failed' && (
          <button
            type="button"
            onClick={() => onRetry(task)}
            disabled={retrying}
            className="inline-flex items-center gap-1 rounded-md border border-ink-300 px-2 py-1 text-[11px] font-medium text-ink-700 hover:border-brand-500 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-ink-600 dark:text-ink-200 dark:hover:border-brand-500"
          >
            <RotateCcw size={11} />
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
        )}
      </div>
    </li>
  );
}

function StatusIcon({ status }: { status: ExtractTaskStatus }) {
  if (status === 'running') return <Loader2 size={14} className="animate-spin text-brand-600 dark:text-brand-100" />;
  if (status === 'done') return <CheckCircle2 size={14} className="text-ok-600 dark:text-ok-500" />;
  if (status === 'failed') return <AlertCircle size={14} className="text-danger-600 dark:text-danger-500" />;
  return <span aria-hidden className="inline-block h-[14px] w-[14px] rounded-full border border-ink-300 dark:border-ink-600" />;
}

function StatusBadgeForStatus({ status }: { status: ExtractTaskStatus }) {
  if (status === 'queued')  return <StatusBadge tone="neutral">Queued</StatusBadge>;
  if (status === 'running') return <StatusBadge tone="brand">Running</StatusBadge>;
  if (status === 'done')    return <StatusBadge tone="ok">Done</StatusBadge>;
  return <StatusBadge tone="danger">Failed</StatusBadge>;
}

function RowSkeleton() {
  return (
    <li className="px-4 py-3 text-sm text-ink-500 dark:text-ink-400">Loading…</li>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <li className="px-4 py-3 text-sm text-ink-500 dark:text-ink-400">{children}</li>;
}
