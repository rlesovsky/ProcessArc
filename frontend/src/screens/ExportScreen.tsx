import { useEffect, useState } from 'react';
import { Download, FileSpreadsheet, FileText, RefreshCw } from 'lucide-react';
import { api, ApiError } from '@/api/client';
import type { ExportFile, ExportResult, PlantConfiguration } from '@/api/types';
import { cn } from '@/lib/cn';

interface ExportScreenProps {
  projectId: string;
  plant: PlantConfiguration;
}

export function ExportScreen({ projectId, plant }: ExportScreenProps) {
  const [result, setResult] = useState<ExportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // On entry: kick the render once (UI §2.5 "On entry, triggers the export").
  // If the engineer comes back from Review after a correction, re-render.
  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.runExport(projectId));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink-900 dark:text-ink-50">Export</h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Two deliverables, ready to hand to UFP — sized to {summarize(plant)}.
        </p>
      </header>

      {error && (
        <div className="rounded-card border border-danger-500/40 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <ResultCard
          title="IO / device list"
          note="Tank rows + standard register block pre-filled; variable registers blank."
          file={result?.io_list}
          downloadUrl={api.downloadIoListUrl(projectId)}
          busy={busy}
          icon={<FileSpreadsheet size={16} className="text-brand-600 dark:text-brand-100" />}
        />
        <ResultCard
          title="Cause & Effect draft"
          note={ceNote(plant)}
          file={result?.ce}
          downloadUrl={api.downloadCeUrl(projectId)}
          busy={busy}
          icon={<FileSpreadsheet size={16} className="text-brand-600 dark:text-brand-100" />}
        />
        <ResultCard
          title="Treating sequence (Word)"
          note="Customer's cylinder + mix prose, formatted with section headings + bold step headers."
          file={result?.sequence_doc}
          downloadUrl={api.downloadSequenceDocUrl(projectId)}
          busy={busy}
          icon={<FileText size={16} className="text-brand-600 dark:text-brand-100" />}
        />
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-ink-500 dark:text-ink-400">
          Made a correction? Use Back to return to Review, edit, then re-export.
        </p>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="inline-flex items-center gap-1 rounded-md border border-ink-300 px-3 py-1.5 text-[11px] font-medium text-ink-700 hover:border-brand-500 hover:text-brand-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-ink-600 dark:text-ink-200"
        >
          <RefreshCw size={11} className={cn(busy && 'animate-spin')} />
          {busy ? 'Re-rendering…' : 'Re-render both'}
        </button>
      </div>
    </section>
  );
}

function summarize(plant: PlantConfiguration): string {
  const active = plant.cylinders.filter(c => !c.is_idle).map(c => c.number);
  const bits: string[] = [];
  if (active.length) bits.push(`Treat ${active.join(', ')}`);
  if (plant.mix_systems.length) bits.push(`${plant.mix_systems.length} mixing system${plant.mix_systems.length === 1 ? '' : 's'}`);
  bits.push(`${plant.tanks.length} tanks`);
  if (plant.erp_number) bits.push(`ERP #${plant.erp_number}`);
  return bits.join(', ');
}

function ceNote(plant: PlantConfiguration): string {
  const active = plant.cylinders.filter(c => !c.is_idle).map(c => `Treat ${c.number}`);
  const mix = plant.mix_systems.map(m => `Mix ${m.number}`);
  const all = [...active, ...mix];
  return all.length > 0 ? `${all.join(' + ')} columns, universal action rules pre-filled.` : 'Universal action rules pre-filled.';
}

function ResultCard({
  title, note, file, downloadUrl, busy, icon,
}: {
  title: string;
  note: string;
  file: ExportFile | null | undefined;
  downloadUrl: string;
  busy: boolean;
  icon: React.ReactNode;
}) {
  const ready = !!file;
  return (
    <div className="rounded-card border border-ink-200 bg-white p-5 dark:border-ink-700 dark:bg-ink-800">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink-900 dark:text-ink-50">
        {icon}
        {title}
      </div>
      <p className="mb-3 text-xs text-ink-500 dark:text-ink-400">{note}</p>
      <div className="mb-3 min-h-[2rem] font-mono text-[11px] text-ink-700 dark:text-ink-200">
        {ready ? file!.filename : busy ? 'Rendering…' : '—'}
      </div>
      <a
        href={downloadUrl}
        download={file?.filename ?? ''}
        aria-disabled={!ready}
        onClick={e => { if (!ready) e.preventDefault(); }}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition',
          ready
            ? 'bg-brand-600 text-white hover:bg-brand-700'
            : 'cursor-not-allowed bg-ink-200 text-ink-500 dark:bg-ink-700 dark:text-ink-400',
        )}
      >
        <Download size={12} />
        Download
      </a>
      {ready && (
        <span className="ml-2 text-[10px] text-ink-500 dark:text-ink-400">
          {Math.round((file!.size_bytes / 1024) * 10) / 10} KB
        </span>
      )}
    </div>
  );
}
