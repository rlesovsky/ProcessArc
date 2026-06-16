import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { cn } from '@/lib/cn';
import {
  buildCommissioningWorkbook,
  downloadBlob,
  type BuildReport,
  type ChangeLogEntry,
} from '@/api/commissioningWorkbook';
import { h1Fluid, screen as screenContainer } from '@/lib/layout';

type View =
  | { kind: 'upload' }
  | { kind: 'busy' }
  | { kind: 'success'; report: BuildReport; downloaded: boolean }
  | { kind: 'error'; message: string };

const ACCEPTED_EXTENSION = '.xlsx';

function isXlsx(file: File): boolean {
  return file.name.toLowerCase().endsWith(ACCEPTED_EXTENSION);
}

export function CommissioningWorkbookTab() {
  const [view, setView] = useState<View>({ kind: 'upload' });
  const [file, setFile] = useState<File | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  // Hold the latest downloadable Blob so the user can re-download
  // without re-running the build.
  const lastDownloadRef = useRef<{ blob: Blob; filename: string } | null>(null);

  function resetToUpload() {
    setView({ kind: 'upload' });
    setFile(null);
    setClientError(null);
    lastDownloadRef.current = null;
  }

  function handlePick(picked: File | null) {
    if (!picked) {
      setFile(null);
      setClientError(null);
      return;
    }
    if (!isXlsx(picked)) {
      setFile(null);
      setClientError(`Only ${ACCEPTED_EXTENSION} files are supported.`);
      return;
    }
    if (picked.size === 0) {
      setFile(null);
      setClientError('The selected file is empty.');
      return;
    }
    setClientError(null);
    setFile(picked);
  }

  async function handleSubmit() {
    if (!file) return;
    setView({ kind: 'busy' });
    const result = await buildCommissioningWorkbook(file);
    if (!result.ok) {
      setView({ kind: 'error', message: result.message });
      return;
    }
    lastDownloadRef.current = { blob: result.blob, filename: result.filename };
    // Auto-trigger the download; the success view also has a button
    // to re-download in case the browser blocked the first attempt.
    downloadBlob(result.blob, result.filename);
    setView({ kind: 'success', report: result.report, downloaded: true });
  }

  function reDownload() {
    const d = lastDownloadRef.current;
    if (d) downloadBlob(d.blob, d.filename);
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className={screenContainer}>
        {(view.kind === 'upload' || view.kind === 'busy') && (
          <UploadCard
            file={file}
            onPick={handlePick}
            onSubmit={handleSubmit}
            busy={view.kind === 'busy'}
            clientError={clientError}
          />
        )}
        {view.kind === 'success' && (
          <SuccessView
            report={view.report}
            onReDownload={reDownload}
            onReset={resetToUpload}
          />
        )}
        {view.kind === 'error' && (
          <ErrorView message={view.message} onReset={resetToUpload} />
        )}
      </div>
    </div>
  );
}

// ─── Upload state ──────────────────────────────────────────────────────────

interface UploadCardProps {
  file: File | null;
  onPick: (file: File | null) => void;
  onSubmit: () => void;
  busy: boolean;
  clientError: string | null;
}

function UploadCard({ file, onPick, onSubmit, busy, clientError }: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const canSubmit = file !== null && !busy;

  function openPicker() {
    inputRef.current?.click();
  }
  function handleZoneKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPicker();
    }
  }

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className={h1Fluid}>Commissioning Workbook Builder</h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Upload the customer write-up workbook (Graphics-and-Tables style).
          We populate the canonical CommWKBK template with the data we can
          safely derive — flow-meter cross-checks, sequence narratives,
          graphic notes, and plant-level facts. The download is a new
          workbook; the original CommWKBK template is unchanged.
        </p>
      </header>

      <div
        role="button"
        tabIndex={busy ? -1 : 0}
        aria-label="Drop the source .xlsx file or press Enter to browse"
        aria-disabled={busy}
        onClick={busy ? undefined : openPicker}
        onKeyDown={busy ? undefined : handleZoneKey}
        onDragOver={(e) => { if (!busy) e.preventDefault(); }}
        onDrop={(e) => {
          if (busy) return;
          e.preventDefault();
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) onPick(dropped);
        }}
        className={cn(
          'flex h-48 flex-col items-center justify-center gap-2 rounded-card border border-dashed p-6 text-center transition-colors',
          busy && 'cursor-not-allowed opacity-60',
          !busy && file
            ? 'cursor-pointer border-ok-500 bg-ok-50 dark:bg-ok-500/10'
            : !busy &&
              'cursor-pointer border-ink-300 bg-white hover:border-brand-500 hover:bg-brand-50 dark:border-ink-600 dark:bg-ink-800 dark:hover:border-brand-500 dark:hover:bg-brand-500/10',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSION}
          className="hidden"
          data-testid="commissioning-workbook-file-input"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />
        <Upload className="text-ink-500 dark:text-ink-400" size={26} aria-hidden />
        {file ? (
          <>
            <div className="font-mono text-xs text-ink-700 dark:text-ink-200 break-all">
              {file.name}
            </div>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onPick(null); }}
              className="text-[11px] text-ink-500 underline-offset-2 hover:underline dark:text-ink-400"
            >
              Clear
            </button>
          </>
        ) : (
          <>
            <div className="text-sm font-medium text-ink-700 dark:text-ink-200">
              Drop the source write-up .xlsx here
            </div>
            <div className="text-[11px] text-ink-500 dark:text-ink-400">
              or click to browse
            </div>
          </>
        )}
      </div>

      {clientError && (
        <div
          role="alert"
          className="rounded-card border border-danger-500/40 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500"
        >
          {clientError}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={onSubmit}
          className={cn(
            'inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors',
            canSubmit
              ? 'bg-brand-500 text-white hover:bg-brand-600'
              : 'cursor-not-allowed bg-ink-200 text-ink-500 dark:bg-ink-700 dark:text-ink-400',
          )}
        >
          {busy ? (
            <>
              <Spinner />
              <span>Building…</span>
            </>
          ) : (
            'Build Workbook'
          )}
        </button>
      </div>
    </section>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
    />
  );
}

// ─── Success state ─────────────────────────────────────────────────────────

interface SuccessViewProps {
  report: BuildReport;
  onReDownload: () => void;
  onReset: () => void;
}

function SuccessView({ report, onReDownload, onReset }: SuccessViewProps) {
  const conflicts = report.changes.filter((c) => c.conflict);
  const writes = report.changes.filter((c) => !c.conflict);
  return (
    <section className="space-y-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className={h1Fluid}>Commissioning Workbook Builder</h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            Populated workbook downloaded. Review the change log below; any
            conflicts (cells we left in place) are flagged.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="rounded-md border border-ink-300 px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-700"
          >
            Build another
          </button>
          <button
            type="button"
            onClick={onReDownload}
            className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
          >
            Download again
          </button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Flow meters" value={report.flow_meters_matched} />
        <StatTile label="Sequence notes" value={report.sequence_notes_attached} />
        <StatTile label="Graphic notes" value={report.graphic_notes_attached} />
        <StatTile label="Plant facts" value={report.plant_facts_attached} />
      </div>

      {report.warnings.length > 0 && (
        <div className="rounded-card border border-warn-500/40 bg-warn-50 px-3 py-2 text-sm text-warn-700 dark:bg-warn-500/10 dark:text-warn-500">
          <div className="font-medium">Warnings ({report.warnings.length})</div>
          <ul className="mt-1 list-disc pl-5 text-xs">
            {report.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <ChangePanel title={`Cells written (${writes.length})`} entries={writes} />
      {conflicts.length > 0 && (
        <ChangePanel
          title={`Conflicts — not overwritten (${conflicts.length})`}
          entries={conflicts}
          isConflict
        />
      )}
    </section>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-card border border-ink-200 bg-white px-3 py-2 dark:border-ink-700 dark:bg-ink-800">
      <div className="text-[11px] uppercase tracking-wide text-ink-500 dark:text-ink-400">
        {label}
      </div>
      <div className="text-lg font-semibold text-ink-900 dark:text-ink-50">
        {value}
      </div>
    </div>
  );
}

interface ChangePanelProps {
  title: string;
  entries: ChangeLogEntry[];
  isConflict?: boolean;
}

function ChangePanel({ title, entries, isConflict }: ChangePanelProps) {
  return (
    <section
      className={cn(
        'rounded-card border bg-white dark:bg-ink-800',
        isConflict
          ? 'border-warn-500/40 dark:border-warn-500/30'
          : 'border-ink-200 dark:border-ink-700',
      )}
    >
      <header className="border-b border-ink-200 px-4 py-3 dark:border-ink-700">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700 dark:text-ink-200">
          {title}
        </h2>
      </header>
      <div className="max-h-96 overflow-auto p-2 text-xs">
        <table className="w-full">
          <thead className="text-[10px] uppercase tracking-wide text-ink-500 dark:text-ink-400">
            <tr>
              <th className="px-2 py-1 text-left">Sheet</th>
              <th className="px-2 py-1 text-left">Cell</th>
              <th className="px-2 py-1 text-left">Before</th>
              <th className="px-2 py-1 text-left">After</th>
              <th className="px-2 py-1 text-left">Reason</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {entries.map((e, i) => (
              <tr
                key={i}
                className="border-t border-ink-100 dark:border-ink-700"
              >
                <td className="px-2 py-1 align-top">{e.sheet}</td>
                <td className="px-2 py-1 align-top">{e.cell}</td>
                <td className="px-2 py-1 align-top text-ink-500 dark:text-ink-400 break-all">
                  {e.before || '∅'}
                </td>
                <td className="px-2 py-1 align-top text-ink-700 dark:text-ink-200 break-all">
                  {e.after}
                </td>
                <td className="px-2 py-1 align-top text-[10px] text-ink-500 dark:text-ink-400">
                  {e.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ─── Error state ───────────────────────────────────────────────────────────

interface ErrorViewProps {
  message: string;
  onReset: () => void;
}

function ErrorView({ message, onReset }: ErrorViewProps) {
  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <header>
        <h1 className={h1Fluid}>Couldn't build the workbook</h1>
        <p className="mt-1 text-sm text-danger-700 dark:text-danger-500">
          {message}
        </p>
      </header>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onReset}
          className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
        >
          Try again
        </button>
      </div>
    </section>
  );
}
