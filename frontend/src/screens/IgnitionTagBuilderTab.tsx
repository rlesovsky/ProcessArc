import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { cn } from '@/lib/cn';
import {
  buildIgnitionTags,
  bundleAsJsonBlob,
  type BuildIgnitionTagsResult,
  type BuildIgnitionTagsSuccess,
  type BuildIgnitionTagsValidationError,
  type IgnitionTagsBundle,
  type ValidationReport,
} from '@/api/ignitionTags';
import { TagBundlePreview } from '@/components/TagBundlePreview';
import { ValidationReportPanel } from '@/components/ValidationReportPanel';
import { h1Fluid, screen as screenContainer } from '@/lib/layout';

type View = { kind: 'upload' } | { kind: 'busy' } | { kind: 'results'; payload: BuildIgnitionTagsSuccess } | { kind: 'error'; payload: ErrorPayload };

interface ErrorPayload {
  message: string;
  /** Only present when the backend returned a structured 400. */
  report?: ValidationReport;
}

const ACCEPTED_EXTENSION = '.xlsx';
const EXTENSION_ERROR = `Only ${ACCEPTED_EXTENSION} files are supported.`;
const EMPTY_FILE_ERROR = 'The selected file is empty.';

function isXlsx(file: File): boolean {
  return file.name.toLowerCase().endsWith(ACCEPTED_EXTENSION);
}

export function IgnitionTagBuilderTab() {
  const [view, setView] = useState<View>({ kind: 'upload' });
  const [file, setFile] = useState<File | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);

  function resetToUpload() {
    setView({ kind: 'upload' });
    setFile(null);
    setClientError(null);
  }

  function handlePick(picked: File | null) {
    if (!picked) {
      setFile(null);
      setClientError(null);
      return;
    }
    if (!isXlsx(picked)) {
      setFile(null);
      setClientError(EXTENSION_ERROR);
      return;
    }
    if (picked.size === 0) {
      setFile(null);
      setClientError(EMPTY_FILE_ERROR);
      return;
    }
    setClientError(null);
    setFile(picked);
  }

  async function handleSubmit() {
    if (!file) return;
    setView({ kind: 'busy' });
    const result: BuildIgnitionTagsResult = await buildIgnitionTags(file);
    if (result.ok) {
      setView({ kind: 'results', payload: result });
      return;
    }
    if (result.kind === 'validation') {
      setView({
        kind: 'error',
        payload: { message: result.message, report: result.report },
      });
      return;
    }
    setView({ kind: 'error', payload: { message: result.message } });
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
        {view.kind === 'results' && (
          <ResultsView payload={view.payload} onReset={resetToUpload} />
        )}
        {view.kind === 'error' && (
          <ErrorView payload={view.payload} onReset={resetToUpload} />
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Upload state
// =============================================================================

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

  // Keyboard-reachable drop zone: button-style activation on Enter/Space.
  function handleZoneKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPicker();
    }
  }

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <header>
        <h1 className={h1Fluid}>
          Ignition Tag Builder
        </h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Upload a populated Ignition tag-list template to generate the Ignition
          tag-instance JSON bundle.
        </p>
      </header>

      <div
        role="button"
        tabIndex={busy ? -1 : 0}
        aria-label="Drop an .xlsx file or press Enter to browse"
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
          data-testid="ignition-tags-file-input"
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
              Drop an .xlsx tag-list template here
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

      <p className="text-xs text-ink-500 dark:text-ink-400">
        Need the template format? See the{' '}
        <a
          href="/docs/ignition_tag_template_spec.md"
          title="Located at docs/ignition_tag_template_spec.md in the ProcessArc repo"
          className="text-brand-600 underline-offset-2 hover:underline dark:text-brand-100"
        >
          template specification
        </a>
        .
      </p>

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
            'Build Tags'
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

// =============================================================================
// Results state
// =============================================================================

interface ResultsViewProps {
  payload: BuildIgnitionTagsSuccess;
  onReset: () => void;
}

function ResultsView({ payload, onReset }: ResultsViewProps) {
  const total = payload.instanceCount;

  function handleDownload() {
    triggerDownload(bundleAsJsonBlob(payload.bundle), payload.filename);
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className={h1Fluid}>
            Ignition Tag Builder
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            Bundle ready. Download the JSON and import it in Ignition Designer.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="rounded-md border border-ink-300 px-3 py-1.5 text-sm text-ink-700 hover:bg-ink-100 dark:border-ink-600 dark:text-ink-200 dark:hover:bg-ink-700"
          >
            Upload another file
          </button>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
          >
            Download JSON
          </button>
        </div>
      </header>

      {/* Stack on phones; go side-by-side at md (≥768px) so the
          validation report and the tree share the viewport as soon as
          there's room. 2/3 split keeps the tree as the visual focus. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        <div className="md:col-span-2">
          <ValidationReportPanel report={payload.report} />
        </div>
        <div className="md:col-span-3">
          <TagBundlePreview bundle={payload.bundle} totalInstances={total} />
        </div>
      </div>
    </section>
  );
}

// =============================================================================
// Error state
// =============================================================================

interface ErrorViewProps {
  payload: ErrorPayload;
  onReset: () => void;
}

function ErrorView({ payload, onReset }: ErrorViewProps) {
  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <header>
        <h1 className={h1Fluid}>
          Couldn't build the bundle
        </h1>
        <p className="mt-1 text-sm text-danger-700 dark:text-danger-500">{payload.message}</p>
      </header>

      {payload.report && <ValidationReportPanel report={payload.report} errorsOnTop />}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onReset}
          className="rounded-md bg-brand-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-600"
        >
          Upload another file
        </button>
      </div>
    </section>
  );
}

// =============================================================================
// Helpers
// =============================================================================

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Release the object URL on the next tick so the click has time to land.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// Re-export for tests
export type { IgnitionTagsBundle, ValidationReport, BuildIgnitionTagsValidationError };
