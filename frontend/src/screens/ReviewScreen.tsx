import { useEffect, useMemo, useState } from 'react';
import { Check, EyeOff, Filter, Pencil, Plus, X } from 'lucide-react';
import { api, ApiError } from '@/api/client';
import type {
  ConfidenceValue,
  DeviceClassValue,
  DeviceModel,
  DeviceRecord,
  PlantConfiguration,
  ReviewStatusValue,
  SystemKindValue,
} from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { cn } from '@/lib/cn';
import { h1Fluid } from '@/lib/layout';

interface ReviewScreenProps {
  projectId: string;
  plant: PlantConfiguration;
  /** Called when save+advance succeeds. App routes the user to Export. */
  onAdvance: () => void;
}

const DEVICE_CLASSES: DeviceClassValue[] = ['Pump', 'Valve', 'VFD Pump', 'Control Valve', 'Tank'];

interface FilterState {
  systemKey: string; // 'all' | 'needs_review' | `cyl:N` | `mix:N`
}

export function ReviewScreen({ projectId, plant, onAdvance }: ReviewScreenProps) {
  const [model, setModel] = useState<DeviceModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [filter, setFilter] = useState<FilterState>({ systemKey: 'all' });

  useEffect(() => {
    (async () => {
      try {
        setModel(await api.getDeviceModel(projectId));
      } catch (e) {
        setError(e instanceof ApiError ? e.detail : (e as Error).message);
      }
    })();
  }, [projectId]);

  const filteredDevices = useMemo(() => {
    if (!model) return [];
    if (filter.systemKey === 'all') return model.devices;
    if (filter.systemKey === 'needs_review') {
      return model.devices.filter(d => d.confidence === 'Needs Review' && d.review_status === 'Pending');
    }
    const [kind, numStr] = filter.systemKey.split(':');
    const num = Number(numStr);
    return model.devices.filter(d =>
      (kind === 'cyl' && d.system === 'Cylinders' && d.system_number === num) ||
      (kind === 'mix' && d.system === 'Mixing' && d.system_number === num),
    );
  }, [model, filter]);

  const unresolvedCount = useMemo(
    () => model?.devices.filter(d => d.confidence === 'Needs Review' && d.review_status === 'Pending').length ?? 0,
    [model],
  );
  const totalCount = model?.devices.length ?? 0;
  const canContinue = model !== null && unresolvedCount === 0;

  function updateDevice(canonicalId: string, patch: Partial<DeviceRecord>) {
    if (!model) return;
    setModel({
      ...model,
      devices: model.devices.map(d => (d.canonical_id === canonicalId ? { ...d, ...patch } : d)),
    });
  }

  function setStatus(d: DeviceRecord, status: ReviewStatusValue) {
    updateDevice(d.canonical_id, { review_status: status });
  }

  function addDevice(payload: NewDevicePayload) {
    if (!model) return;
    // Build a minimal canonical id consistent with the backend convention.
    const sys = payload.system === 'Cylinders' ? 'CYL' : 'MIX';
    const num = payload.system_number != null ? String(payload.system_number) : 'X';
    const clean = payload.base_name.replace(/[^A-Za-z0-9]/g, '').toUpperCase() || 'UNNAMED';
    const baseId = `${sys}${num}_${clean}`;
    let canonical_id = baseId;
    let i = 2;
    const taken = new Set(model.devices.map(d => d.canonical_id));
    while (taken.has(canonical_id)) {
      canonical_id = `${baseId}_${i++}`;
    }
    const newDevice: DeviceRecord = {
      canonical_id,
      device_class: payload.device_class,
      system: payload.system,
      system_number: payload.system_number,
      base_name: payload.base_name,
      description: payload.description,
      source_reference: '',
      source_type: 'Manual',
      confidence: 'High',
      ignition_udt_type: '',
      ignition_folder: '',
      ce_output_tag: '',
      register_values: {},
      notes: '',
      review_status: 'Confirmed',
    };
    setModel({ ...model, devices: [...model.devices, newDevice] });
    setAddOpen(false);
  }

  async function saveAndContinue() {
    if (!model) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.saveDeviceModel(projectId, model);
      if (res.advanced) onAdvance();
      else setError('Some flagged devices still need to be resolved before continuing.');
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // ── Chip definitions for the filter row, built from the live Plant Config.
  const chips: { key: string; label: string; tone?: 'brand' | 'warn' }[] = [
    { key: 'all', label: `All (${totalCount})` },
    ...plant.cylinders
      .filter(c => !c.is_idle)
      .map(c => ({ key: `cyl:${c.number}`, label: `Cylinder ${c.number}` })),
    ...plant.mix_systems.map(m => ({ key: `mix:${m.number}`, label: m.name || `Mixing ${m.number}` })),
  ];
  if (unresolvedCount > 0) {
    chips.push({ key: 'needs_review', label: `Needs review (${unresolvedCount})`, tone: 'warn' });
  }

  return (
    <section className="space-y-5">
      {/* Banner restating Plant Config (UI §2.4) */}
      <header className="rounded-card border border-ink-200 bg-white p-4 dark:border-ink-700 dark:bg-ink-800">
        <h1 className={h1Fluid}>Review devices</h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          {plantSummary(plant)}
        </p>
        <p className="mt-2 text-sm font-medium text-ink-700 dark:text-ink-200">
          {totalCount} {totalCount === 1 ? 'device' : 'devices'}
          {unresolvedCount > 0 && (
            <>
              {' · '}
              <span className="text-warn-700 dark:text-warn-500">
                {unresolvedCount} need{unresolvedCount === 1 ? 's' : ''} review
              </span>
            </>
          )}
        </p>
      </header>

      {error && (
        <div className="rounded-card border border-danger-500/40 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500">
          {error}
        </div>
      )}

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter size={12} className="text-ink-500 dark:text-ink-400" aria-hidden />
        {chips.map(chip => {
          const active = filter.systemKey === chip.key;
          return (
            <button
              key={chip.key}
              type="button"
              onClick={() => setFilter({ systemKey: chip.key })}
              className={cn(
                'rounded-full border px-3 py-1 text-[11px] font-medium transition',
                active
                  ? 'border-brand-500 bg-brand-500 text-white'
                  : chip.tone === 'warn'
                    ? 'border-warn-500/40 bg-warn-50 text-warn-700 hover:bg-warn-100 dark:bg-warn-500/10 dark:text-warn-500'
                    : 'border-ink-300 bg-white text-ink-700 hover:border-brand-500 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-200',
              )}
            >
              {chip.label}
            </button>
          );
        })}
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          className="inline-flex items-center gap-1 rounded-md border border-ink-300 px-3 py-1 text-[11px] font-medium text-ink-700 hover:border-brand-500 hover:text-brand-700 dark:border-ink-600 dark:text-ink-200"
        >
          <Plus size={12} />
          Add device
        </button>
      </div>

      {/* Device grid */}
      <div className="overflow-hidden rounded-card border border-ink-200 dark:border-ink-700">
        <table className="w-full border-collapse text-xs">
          <thead className="bg-ink-50 dark:bg-ink-900">
            <tr className="text-left text-[11px] font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400">
              <th className="px-3 py-2">Device</th>
              <th className="px-3 py-2">Class</th>
              <th className="px-3 py-2">System</th>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100 dark:divide-ink-700">
            {filteredDevices.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-sm text-ink-500 dark:text-ink-400">
                  {model === null ? 'Loading…' : 'No devices match this filter.'}
                </td>
              </tr>
            )}
            {filteredDevices.map(d => (
              <DeviceRow
                key={d.canonical_id}
                device={d}
                isEditing={editing === d.canonical_id}
                onStartEdit={() => setEditing(d.canonical_id)}
                onCancelEdit={() => setEditing(null)}
                onChange={patch => updateDevice(d.canonical_id, patch)}
                onConfirm={() => setStatus(d, 'Confirmed')}
                onExclude={() => setStatus(d, 'Excluded')}
                onReinstate={() => setStatus(d, 'Confirmed')}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <p className="text-[11px] text-ink-500 dark:text-ink-400">
          {canContinue
            ? 'All flagged devices resolved — ready to export.'
            : `Resolve the remaining ${unresolvedCount} flagged device${unresolvedCount === 1 ? '' : 's'} (confirm, edit, or exclude) before continuing.`}
        </p>
        <button
          type="button"
          onClick={saveAndContinue}
          disabled={busy || !canContinue}
          className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save & continue to Export →'}
        </button>
      </div>

      {addOpen && (
        <AddDeviceModal
          plant={plant}
          onClose={() => setAddOpen(false)}
          onAdd={addDevice}
        />
      )}
    </section>
  );
}

// ── Plant summary line for the banner.
function plantSummary(plant: PlantConfiguration): string {
  const active = plant.cylinders.filter(c => !c.is_idle).map(c => c.number);
  const idle = plant.cylinders.filter(c => c.is_idle).map(c => c.number);
  const bits: string[] = [];
  if (active.length) bits.push(`Cylinders ${active.join(', ')} active`);
  if (idle.length) bits.push(`${idle.length} idle`);
  if (plant.mix_systems.length) {
    bits.push(`${plant.mix_systems.length} mixing system${plant.mix_systems.length === 1 ? '' : 's'}`);
  }
  bits.push(`${plant.tanks.length} tanks`);
  if (plant.erp_number) bits.push(`ERP #${plant.erp_number}`);
  return bits.join(' · ');
}

// ─────────────────────────────────────────────────────────────────────────────
// Device row — display + inline edit
// ─────────────────────────────────────────────────────────────────────────────
interface DeviceRowProps {
  device: DeviceRecord;
  isEditing: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onChange: (patch: Partial<DeviceRecord>) => void;
  onConfirm: () => void;
  onExclude: () => void;
  onReinstate: () => void;
}

function DeviceRow({
  device, isEditing, onStartEdit, onCancelEdit, onChange,
  onConfirm, onExclude, onReinstate,
}: DeviceRowProps) {
  const isExcluded = device.review_status === 'Excluded';
  const isFlagged = device.confidence === 'Needs Review' && device.review_status === 'Pending';
  const isConfirmed = device.review_status === 'Confirmed';

  return (
    <tr className={cn(
      isFlagged && 'bg-warn-50 dark:bg-warn-500/10',
      isExcluded && 'opacity-60',
    )}>
      <td className="px-3 py-2">
        {isEditing ? (
          <input
            value={device.base_name}
            onChange={e => onChange({ base_name: e.target.value })}
            className="w-28 rounded border border-ink-300 px-1.5 py-0.5 font-mono text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
          />
        ) : (
          <span className={cn(
            'font-mono',
            isExcluded && 'line-through',
          )}>{device.base_name}</span>
        )}
      </td>
      <td className="px-3 py-2">
        {isEditing ? (
          <select
            value={device.device_class}
            onChange={e => onChange({ device_class: e.target.value as DeviceClassValue })}
            className="rounded border border-ink-300 px-1 py-0.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
          >
            {DEVICE_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        ) : (
          <span className="text-ink-700 dark:text-ink-200">{device.device_class}</span>
        )}
      </td>
      <td className="px-3 py-2 text-ink-700 dark:text-ink-200">
        {device.system === 'Cylinders' ? `Cyl ${device.system_number ?? '–'}` : `Mix ${device.system_number ?? '–'}`}
      </td>
      <td className="px-3 py-2">
        {isEditing ? (
          <input
            value={device.description}
            onChange={e => onChange({ description: e.target.value })}
            className="w-full rounded border border-ink-300 px-1.5 py-0.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
          />
        ) : (
          <span className="text-ink-700 dark:text-ink-200">{device.description || <em className="text-ink-400">—</em>}</span>
        )}
      </td>
      <td className="px-3 py-2">
        {isExcluded
          ? <StatusBadge tone="neutral">Excluded</StatusBadge>
          : isConfirmed
            ? <StatusBadge tone="ok">Confirmed</StatusBadge>
            : isFlagged
              ? <StatusBadge tone="warn">Low confidence</StatusBadge>
              : <StatusBadge tone="neutral">Pending</StatusBadge>}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-1">
          {isEditing ? (
            <button
              type="button"
              onClick={onCancelEdit}
              className="rounded p-1 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-700"
              title="Done"
            >
              <Check size={12} />
            </button>
          ) : (
            <button
              type="button"
              onClick={onStartEdit}
              className="rounded p-1 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-700"
              title="Edit"
            >
              <Pencil size={12} />
            </button>
          )}
          {!isExcluded && !isConfirmed && (
            <button
              type="button"
              onClick={onConfirm}
              className="rounded p-1 text-ok-600 hover:bg-ok-50 dark:hover:bg-ok-500/15"
              title="Confirm"
            >
              <Check size={12} />
            </button>
          )}
          {!isExcluded && (
            <button
              type="button"
              onClick={onExclude}
              className="rounded p-1 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-700"
              title="Exclude"
            >
              <EyeOff size={12} />
            </button>
          )}
          {isExcluded && (
            <button
              type="button"
              onClick={onReinstate}
              className="rounded p-1 text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-500/15"
              title="Reinstate"
            >
              <Check size={12} />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Add device modal
// ─────────────────────────────────────────────────────────────────────────────
interface NewDevicePayload {
  base_name: string;
  device_class: DeviceClassValue;
  system: SystemKindValue;
  system_number: number | null;
  description: string;
  confidence: ConfidenceValue;
}

function AddDeviceModal({
  plant, onClose, onAdd,
}: {
  plant: PlantConfiguration;
  onClose: () => void;
  onAdd: (payload: NewDevicePayload) => void;
}) {
  const cylNums = plant.cylinders.filter(c => !c.is_idle).map(c => c.number);
  const mixNums = plant.mix_systems.map(m => m.number);
  const initialSystem: SystemKindValue = cylNums.length ? 'Cylinders' : 'Mixing';
  const [system, setSystem] = useState<SystemKindValue>(initialSystem);
  const [systemNumber, setSystemNumber] = useState<number | null>(
    initialSystem === 'Cylinders' ? cylNums[0] ?? null : mixNums[0] ?? null,
  );
  const [baseName, setBaseName] = useState('');
  const [deviceClass, setDeviceClass] = useState<DeviceClassValue>('Valve');
  const [description, setDescription] = useState('');

  const numbers = system === 'Cylinders' ? cylNums : mixNums;
  const canAdd = baseName.trim().length > 0 && systemNumber !== null;

  return (
    <div
      role="dialog"
      aria-label="Add device"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-card border border-ink-200 bg-white p-5 shadow-xl dark:border-ink-700 dark:bg-ink-800"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-900 dark:text-ink-50">Add a device</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-500 hover:bg-ink-100 dark:text-ink-400 dark:hover:bg-ink-700">
            <X size={14} />
          </button>
        </div>
        <p className="mb-3 text-[11px] text-ink-500 dark:text-ink-400">
          Use this when a device is real but absent from the prose (e.g. V9 in the Fairless Hills case).
        </p>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Base name">
            <input
              value={baseName}
              onChange={e => setBaseName(e.target.value)}
              placeholder="V9"
              className="w-full rounded-md border border-ink-300 px-2 py-1.5 font-mono text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
              autoFocus
            />
          </Field>
          <Field label="Class">
            <select
              value={deviceClass}
              onChange={e => setDeviceClass(e.target.value as DeviceClassValue)}
              className="w-full rounded-md border border-ink-300 px-2 py-1.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
            >
              {DEVICE_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="System">
            <select
              value={system}
              onChange={e => {
                const next = e.target.value as SystemKindValue;
                setSystem(next);
                const nextNums = next === 'Cylinders' ? cylNums : mixNums;
                setSystemNumber(nextNums[0] ?? null);
              }}
              className="w-full rounded-md border border-ink-300 px-2 py-1.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
            >
              <option value="Cylinders">Cylinders</option>
              <option value="Mixing">Mixing</option>
            </select>
          </Field>
          <Field label="Number">
            <select
              value={systemNumber ?? ''}
              onChange={e => setSystemNumber(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-md border border-ink-300 px-2 py-1.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
            >
              {numbers.map(n => <option key={n} value={n}>{n}</option>)}
              {numbers.length === 0 && <option value="">—</option>}
            </select>
          </Field>
          <div className="col-span-2">
            <Field label="Description">
              <input
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Vacuum break valve"
                className="w-full rounded-md border border-ink-300 px-2 py-1.5 text-xs dark:border-ink-600 dark:bg-ink-900 dark:text-ink-50"
              />
            </Field>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="text-[11px] font-medium text-ink-500 hover:text-ink-700 dark:text-ink-400">
            Cancel
          </button>
          <button
            type="button"
            disabled={!canAdd}
            onClick={() => onAdd({
              base_name: baseName.trim(),
              device_class: deviceClass,
              system,
              system_number: systemNumber,
              description: description.trim(),
              confidence: 'High',
            })}
            className="inline-flex items-center gap-1 rounded-md bg-brand-600 px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Add device
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-ink-500 dark:text-ink-400">
        {label}
      </span>
      {children}
    </label>
  );
}
