import { useRef, useState } from 'react';
import { Upload } from 'lucide-react';
import { cn } from '@/lib/cn';
import {
  buildIgnitionTags,
  buildPlantBundle,
  bundleAsJsonBlob,
  type BuildIgnitionTagsResult,
  type BuildIgnitionTagsSuccess,
  type BuildIgnitionTagsValidationError,
  type IgnitionTagsBundle,
  type PlantBundleConfig,
  type ValidationReport,
} from '@/api/ignitionTags';
import { TagBundlePreview } from '@/components/TagBundlePreview';
import { ValidationReportPanel } from '@/components/ValidationReportPanel';
import { h1Fluid, screen as screenContainer } from '@/lib/layout';

type Mode = 'xlsx' | 'plant';

type View =
  | { kind: 'upload' }
  | { kind: 'busy' }
  | { kind: 'results'; payload: BuildIgnitionTagsSuccess }
  | { kind: 'error'; payload: ErrorPayload };

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
  const [mode, setMode] = useState<Mode>('xlsx');
  const [view, setView] = useState<View>({ kind: 'upload' });
  const [file, setFile] = useState<File | null>(null);
  const [clientError, setClientError] = useState<string | null>(null);

  function resetToUpload() {
    setView({ kind: 'upload' });
    setFile(null);
    setClientError(null);
  }

  function handleModeChange(next: Mode) {
    if (next === mode) return;
    setMode(next);
    resetToUpload();
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

  async function handleSubmitXlsx() {
    if (!file) return;
    setView({ kind: 'busy' });
    const result: BuildIgnitionTagsResult = await buildIgnitionTags(file);
    handleResult(result);
  }

  async function handleSubmitPlant(config: PlantBundleConfig, xlsx: File | null) {
    setView({ kind: 'busy' });
    const result = await buildPlantBundle(config, xlsx);
    handleResult(result);
  }

  function handleResult(result: BuildIgnitionTagsResult) {
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
          <section className="mx-auto max-w-2xl space-y-4">
            <header>
              <h1 className={h1Fluid}>Ignition Tag Builder</h1>
              <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
                {mode === 'xlsx'
                  ? 'Upload a populated Ignition tag-list template to generate the Ignition tag-instance JSON bundle.'
                  : 'Build a complete Ignition tag bundle for a new UFP plant from the committed donor library.'}
              </p>
            </header>

            <ModeSwitcher mode={mode} onChange={handleModeChange} disabled={view.kind === 'busy'} />

            {mode === 'xlsx' && (
              <UploadCard
                file={file}
                onPick={handlePick}
                onSubmit={handleSubmitXlsx}
                busy={view.kind === 'busy'}
                clientError={clientError}
              />
            )}
            {mode === 'plant' && (
              <PlantBundleForm onSubmit={handleSubmitPlant} busy={view.kind === 'busy'} />
            )}
          </section>
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
// Mode switcher
// =============================================================================

interface ModeSwitcherProps {
  mode: Mode;
  onChange: (next: Mode) => void;
  disabled: boolean;
}

function ModeSwitcher({ mode, onChange, disabled }: ModeSwitcherProps) {
  return (
    <div
      role="tablist"
      aria-label="Build mode"
      className="inline-flex rounded-md border border-ink-300 dark:border-ink-600"
    >
      {(['xlsx', 'plant'] as const).map((key) => {
        const active = mode === key;
        const label = key === 'xlsx' ? 'Build from xlsx' : 'Build full plant bundle';
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active}
            disabled={disabled}
            onClick={() => onChange(key)}
            className={cn(
              'px-3 py-1.5 text-sm transition-colors',
              active
                ? 'bg-brand-500 text-white'
                : 'bg-transparent text-ink-700 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-700',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// =============================================================================
// Upload state — Build from xlsx (existing flow)
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

  function handleZoneKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openPicker();
    }
  }

  return (
    <div className="space-y-6">
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
    </div>
  );
}

// =============================================================================
// Plant bundle form — new flow
// =============================================================================

interface PlantBundleFormProps {
  onSubmit: (config: PlantBundleConfig, xlsx: File | null) => void;
  busy: boolean;
}

interface PlantFormState {
  siteLong: string;
  siteShort: string;
  plantNumber: string;
  regionCode: string;
  cylinderCount: string; // '1' | '2' | '3' — stored as string for input control
  cylinderNumbering: string;
  mixCount: string;
  mixNumbering: string;
  xlsxFile: File | null;
  confirmed: boolean;
}

const INITIAL_PLANT_FORM: PlantFormState = {
  siteLong: '',
  siteShort: '',
  plantNumber: '',
  regionCode: '',
  cylinderCount: '2',
  cylinderNumbering: '',
  mixCount: '2',
  mixNumbering: '',
  xlsxFile: null,
  confirmed: false,
};

function PlantBundleForm({ onSubmit, busy }: PlantBundleFormProps) {
  const [form, setForm] = useState<PlantFormState>(INITIAL_PLANT_FORM);
  const [clientError, setClientError] = useState<string | null>(null);
  const xlsxInputRef = useRef<HTMLInputElement>(null);

  function update<K extends keyof PlantFormState>(key: K, value: PlantFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setClientError(null);
  }

  function parseNumbering(raw: string, count: number): number[] | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const parts = trimmed.split(',').map((s) => s.trim()).filter(Boolean);
    if (parts.length !== count) {
      throw new Error(
        `Numbering list must have exactly ${count} entries (got ${parts.length}).`,
      );
    }
    const nums = parts.map((p) => {
      const n = parseInt(p, 10);
      if (!Number.isFinite(n) || n <= 0) {
        throw new Error(`Numbering entry "${p}" is not a positive integer.`);
      }
      return n;
    });
    return nums;
  }

  const requiredFieldsFilled =
    form.siteLong.trim() !== '' &&
    form.siteShort.trim() !== '' &&
    form.plantNumber.trim() !== '' &&
    form.regionCode.trim() !== '';

  const canSubmit = !busy && requiredFieldsFilled && form.confirmed;

  function handleSubmit() {
    try {
      const cylCount = parseInt(form.cylinderCount, 10);
      const mixCount = parseInt(form.mixCount, 10);
      const cylNumbering = parseNumbering(form.cylinderNumbering, cylCount);
      const mixNumbering = parseNumbering(form.mixNumbering, mixCount);

      const config: PlantBundleConfig = {
        site_long: form.siteLong.trim(),
        site_short: form.siteShort.trim(),
        plant_number: form.plantNumber.trim(),
        region_code: form.regionCode.trim(),
        cylinders: {
          count: cylCount,
          ...(cylNumbering ? { numbering: cylNumbering } : {}),
        },
        mixing: {
          count: mixCount,
          ...(mixNumbering ? { numbering: mixNumbering } : {}),
        },
      };
      onSubmit(config, form.xlsxFile);
    } catch (e) {
      setClientError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Site long name" hint='e.g. "Fairless Hills PA 532"'>
          <input
            type="text"
            value={form.siteLong}
            onChange={(e) => update('siteLong', e.target.value)}
            disabled={busy}
            className={textInputClass}
            data-testid="plant-site-long"
          />
        </Field>
        <Field label="Site short name" hint='e.g. "Fairless Hills"'>
          <input
            type="text"
            value={form.siteShort}
            onChange={(e) => update('siteShort', e.target.value)}
            disabled={busy}
            className={textInputClass}
            data-testid="plant-site-short"
          />
        </Field>
        <Field label="Plant number" hint='e.g. "532"'>
          <input
            type="text"
            value={form.plantNumber}
            onChange={(e) => update('plantNumber', e.target.value)}
            disabled={busy}
            className={textInputClass}
            data-testid="plant-number"
          />
        </Field>
        <Field label="Region code" hint='Two-letter state code, e.g. "PA"'>
          <input
            type="text"
            value={form.regionCode}
            onChange={(e) => update('regionCode', e.target.value)}
            disabled={busy}
            maxLength={2}
            className={textInputClass}
            data-testid="plant-region-code"
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Cylinder count" hint="1, 2, or 3">
          <select
            value={form.cylinderCount}
            onChange={(e) => update('cylinderCount', e.target.value)}
            disabled={busy}
            className={textInputClass}
            data-testid="plant-cyl-count"
          >
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
          </select>
        </Field>
        <Field
          label="Cylinder numbering"
          hint='Comma-separated list, e.g. "1, 3" — optional, defaults to sequential'
        >
          <input
            type="text"
            value={form.cylinderNumbering}
            onChange={(e) => update('cylinderNumbering', e.target.value)}
            disabled={busy}
            placeholder="(sequential)"
            className={textInputClass}
            data-testid="plant-cyl-numbering"
          />
        </Field>
        <Field label="Mix system count" hint="1, 2, or 3">
          <select
            value={form.mixCount}
            onChange={(e) => update('mixCount', e.target.value)}
            disabled={busy}
            className={textInputClass}
            data-testid="plant-mix-count"
          >
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
          </select>
        </Field>
        <Field
          label="Mix system numbering"
          hint='Comma-separated list — optional, defaults to sequential'
        >
          <input
            type="text"
            value={form.mixNumbering}
            onChange={(e) => update('mixNumbering', e.target.value)}
            disabled={busy}
            placeholder="(sequential)"
            className={textInputClass}
            data-testid="plant-mix-numbering"
          />
        </Field>
      </div>

      <Field
        label="PLC-team xlsx (optional)"
        hint="If provided, Pumps/Valves/Tanks UdtInstances from the workbook replace the donor's defaults."
      >
        <input
          ref={xlsxInputRef}
          type="file"
          accept={ACCEPTED_EXTENSION}
          disabled={busy}
          onChange={(e) => update('xlsxFile', e.target.files?.[0] ?? null)}
          className="text-sm text-ink-700 dark:text-ink-200"
          data-testid="plant-xlsx-file"
        />
        {form.xlsxFile && (
          <div className="mt-1 font-mono text-xs text-ink-600 dark:text-ink-300">
            {form.xlsxFile.name}
          </div>
        )}
      </Field>

      <label className="flex items-start gap-2 text-sm text-ink-700 dark:text-ink-200">
        <input
          type="checkbox"
          checked={form.confirmed}
          onChange={(e) => update('confirmed', e.target.checked)}
          disabled={busy}
          className="mt-0.5"
          data-testid="plant-confirm"
        />
        <span>
          I&apos;ve confirmed the cylinder and mix-system counts against the customer&apos;s
          sequence workbook.
        </span>
      </label>

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
          onClick={handleSubmit}
          data-testid="plant-build-button"
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
            'Build Plant Bundle'
          )}
        </button>
      </div>
    </div>
  );
}

const textInputClass =
  'w-full rounded-md border border-ink-300 bg-white px-2 py-1.5 text-sm text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-100';

interface FieldProps {
  label: string;
  hint?: string;
  children: React.ReactNode;
}

function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium text-ink-700 dark:text-ink-200">{label}</div>
      {children}
      {hint && (
        <div className="mt-1 text-[11px] text-ink-500 dark:text-ink-400">{hint}</div>
      )}
    </label>
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
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// Re-export for tests
export type { IgnitionTagsBundle, ValidationReport, BuildIgnitionTagsValidationError };
