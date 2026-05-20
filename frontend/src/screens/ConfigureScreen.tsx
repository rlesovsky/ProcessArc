import { UploadSlot } from '@/components/UploadSlot';

export interface ConfigureState {
  sequenceWorkbook: File | null;
  ioTemplate: File | null;
  ceProfile: File | null;
  projectName: string;
}

interface ConfigureScreenProps {
  value: ConfigureState;
  onChange: (next: ConfigureState) => void;
}

export function ConfigureScreen({ value, onChange }: ConfigureScreenProps) {
  const set = <K extends keyof ConfigureState>(k: K, v: ConfigureState[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-ink-900 dark:text-ink-50">Configure project</h1>
        <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
          Supply the three input files. ProcessArc will then read the sheets and build the Plant Configuration.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <UploadSlot
          label="Sequence workbook"
          required
          hint="UFP graphics-and-sequence .xlsx"
          file={value.sequenceWorkbook}
          onPick={(f) => set('sequenceWorkbook', f)}
        />
        <UploadSlot
          label="UFP IO template"
          required
          hint="Ignition tag-list template .xlsx"
          file={value.ioTemplate}
          onPick={(f) => set('ioTemplate', f)}
        />
        <UploadSlot
          label="C&E profile"
          hint="Optional — default UFP profile used if absent"
          file={value.ceProfile}
          onPick={(f) => set('ceProfile', f)}
        />
      </div>

      <div className="max-w-md">
        <label className="mb-1 block text-sm font-medium text-ink-700 dark:text-ink-200" htmlFor="proj-name">
          Project name
        </label>
        <input
          id="proj-name"
          type="text"
          placeholder="Defaults to the site name from the workbook"
          value={value.projectName}
          onChange={(e) => set('projectName', e.target.value)}
          className="w-full rounded-md border border-ink-300 bg-white px-3 py-1.5 text-sm placeholder:text-ink-300 focus:border-brand-500 focus:outline-none dark:border-ink-600 dark:bg-ink-800 dark:text-ink-100 dark:placeholder:text-ink-500"
        />
      </div>
    </section>
  );
}

export function configureIsReady(s: ConfigureState): boolean {
  return s.sequenceWorkbook !== null && s.ioTemplate !== null;
}
