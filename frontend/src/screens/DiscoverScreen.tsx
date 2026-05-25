import { AlertTriangle } from 'lucide-react';
import type { PlantConfiguration } from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { h1Fluid } from '@/lib/layout';

interface DiscoverScreenProps {
  plant: PlantConfiguration;
  onTogglePlantIdle: (next: PlantConfiguration) => void;
}

export function DiscoverScreen({ plant, onTogglePlantIdle }: DiscoverScreenProps) {
  const active = plant.cylinders.filter(c => !c.is_idle);
  const idle = plant.cylinders.filter(c => c.is_idle);
  const workTanks = plant.tanks.filter(t => t.cylinder_used != null);
  const supplyTanks = plant.tanks.filter(t => t.cylinder_used == null);

  const toggleCyl = (n: number) => {
    onTogglePlantIdle({
      ...plant,
      cylinders: plant.cylinders.map(c =>
        c.number === n ? { ...c, is_idle: !c.is_idle } : c,
      ),
    });
  };

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className={h1Fluid}>
            Confirm Plant Configuration
          </h1>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
            ProcessArc found this from{' '}
            <span className="font-mono text-[12px]">{plant.workbook_filename}</span>. Confirm before continuing.
          </p>
        </div>
        <div className="sm:w-44">
          <label
            htmlFor="erp-number"
            className="mb-1 block text-[11px] font-medium text-ink-600 dark:text-ink-300"
          >
            ERP plant #
          </label>
          <input
            id="erp-number"
            type="text"
            inputMode="numeric"
            value={plant.erp_number}
            onChange={e =>
              onTogglePlantIdle({ ...plant, erp_number: e.target.value.replace(/[^0-9]/g, '') })
            }
            placeholder="e.g. 554"
            maxLength={6}
            className="w-full rounded-md border border-ink-300 bg-white px-2 py-1.5 font-mono text-sm text-ink-900 outline-none focus:border-brand-500 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
          />
          <p className="mt-1 text-[10px] text-ink-500 dark:text-ink-400">
            UFP ERP number — used in Ignition tag paths.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <ConfigCard title="Cylinders">
          <div className="flex flex-wrap gap-2">
            {plant.cylinders.length === 0 && (
              <span className="text-sm text-ink-500 dark:text-ink-400">None discovered</span>
            )}
            {plant.cylinders.map(c => (
              <button
                key={c.number}
                type="button"
                onClick={() => toggleCyl(c.number)}
                title="Click to toggle idle"
                className="rounded-md border border-ink-200 px-3 py-1.5 text-left hover:border-brand-500 dark:border-ink-700 dark:hover:border-brand-500"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-ink-900 dark:text-ink-50">Cylinder {c.number}</span>
                  {c.is_idle
                    ? <StatusBadge tone="neutral">Idle</StatusBadge>
                    : <StatusBadge tone="ok">Active</StatusBadge>}
                </div>
                {c.sequence_sheet && (
                  <div className="font-mono text-[11px] text-ink-500 dark:text-ink-400">
                    {c.sequence_sheet}
                  </div>
                )}
                {c.status_note && (
                  <div className="text-[11px] text-ink-500 dark:text-ink-400">{c.status_note}</div>
                )}
              </button>
            ))}
          </div>
          <Summary text={`${active.length} active${idle.length ? ` · ${idle.length} idle` : ''}`} />
        </ConfigCard>

        <ConfigCard title="Mixing systems">
          <div className="flex flex-wrap gap-2">
            {plant.mix_systems.length === 0 && (
              <span className="text-sm text-ink-500 dark:text-ink-400">None discovered</span>
            )}
            {plant.mix_systems.map(m => (
              <div
                key={m.number}
                className="rounded-md border border-ink-200 px-3 py-1.5 dark:border-ink-700"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-ink-900 dark:text-ink-50">{m.name}</span>
                  {m.chemistry && <StatusBadge tone="brand">{m.chemistry}</StatusBadge>}
                </div>
                {m.sequence_sheet && (
                  <div className="font-mono text-[11px] text-ink-500 dark:text-ink-400">
                    {m.sequence_sheet}
                  </div>
                )}
              </div>
            ))}
          </div>
          <Summary text={`${plant.mix_systems.length} ${plant.mix_systems.length === 1 ? 'system' : 'systems'}`} />
        </ConfigCard>

        <ConfigCard title="Tanks">
          <div className="text-sm text-ink-700 dark:text-ink-200">
            {plant.tanks.length === 0
              ? <span className="text-ink-500 dark:text-ink-400">No tanks found</span>
              : (
                <div className="space-y-1">
                  <div>{plant.tanks.length} total — {workTanks.length} work, {supplyTanks.length} supply</div>
                  {plant.tanks.some(t => t.is_idle) && (
                    <div className="text-warn-700 dark:text-warn-500">
                      {plant.tanks.filter(t => t.is_idle).length} flagged idle
                    </div>
                  )}
                </div>
              )}
          </div>
          <TankBreakdown plant={plant} />
        </ConfigCard>

        <ConfigCard title="Sequence sheets">
          <ul className="space-y-1 text-sm text-ink-700 dark:text-ink-200">
            {plant.sequence_sheets.map(s => (
              <li key={s} className="font-mono text-[12px]">{s}</li>
            ))}
          </ul>
          <Summary text={`${plant.sequence_sheets.length} found in workbook`} />
        </ConfigCard>
      </div>

      {plant.warnings.length > 0 && (
        <div className="rounded-card border border-warn-500/40 bg-warn-50 p-3 dark:bg-warn-500/10">
          <div className="mb-1 flex items-center gap-2 text-sm font-medium text-warn-700 dark:text-warn-500">
            <AlertTriangle size={14} />
            Warnings
          </div>
          <ul className="ml-5 list-disc text-[12px] text-warn-700 dark:text-warn-500">
            {plant.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

function ConfigCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-ink-200 bg-white p-4 dark:border-ink-700 dark:bg-ink-800">
      <h2 className="mb-3 text-sm font-medium text-ink-700 dark:text-ink-200">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Summary({ text }: { text: string }) {
  return (
    <div className="border-t border-ink-100 pt-2 text-[11px] text-ink-500 dark:border-ink-700 dark:text-ink-400">
      {text}
    </div>
  );
}

function TankBreakdown({ plant }: { plant: PlantConfiguration }) {
  const byCyl = new Map<number, number>();
  for (const t of plant.tanks) {
    if (t.cylinder_used != null) {
      byCyl.set(t.cylinder_used, (byCyl.get(t.cylinder_used) ?? 0) + 1);
    }
  }
  if (byCyl.size === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 border-t border-ink-100 pt-2 dark:border-ink-700">
      {[...byCyl.entries()].sort(([a],[b]) => a - b).map(([cyl, n]) => (
        <StatusBadge key={cyl} tone="neutral">Cyl {cyl}: {n}</StatusBadge>
      ))}
    </div>
  );
}
