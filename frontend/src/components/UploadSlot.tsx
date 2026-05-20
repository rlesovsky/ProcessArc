import { Check, Upload } from 'lucide-react';
import { useRef } from 'react';
import { cn } from '@/lib/cn';

interface UploadSlotProps {
  label: string;
  required?: boolean;
  hint?: string;
  file: File | null;
  onPick: (file: File | null) => void;
  accept?: string;
}

export function UploadSlot({ label, required, hint, file, onPick, accept = '.xlsx,.xlsm' }: UploadSlotProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); }}
      onDrop={(e) => {
        e.preventDefault();
        const dropped = e.dataTransfer.files?.[0];
        if (dropped) onPick(dropped);
      }}
      className={cn(
        'flex h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-card border border-dashed p-4 text-center transition-colors',
        file
          ? 'border-ok-500 bg-ok-50 dark:bg-ok-500/10'
          : 'border-ink-300 bg-white hover:border-brand-500 hover:bg-brand-50 dark:border-ink-600 dark:bg-ink-800 dark:hover:border-brand-500 dark:hover:bg-brand-500/10',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
      {file ? (
        <>
          <Check className="text-ok-600 dark:text-ok-500" size={22} />
          <div className="font-mono text-xs text-ink-700 dark:text-ink-200 break-all">{file.name}</div>
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
          <Upload className="text-ink-500 dark:text-ink-400" size={22} />
          <div className="text-sm font-medium text-ink-700 dark:text-ink-200">
            {label}{required && <span className="ml-1 text-danger-500">*</span>}
          </div>
          {hint && <div className="text-[11px] text-ink-500 dark:text-ink-400">{hint}</div>}
          <div className="text-[11px] text-ink-500 dark:text-ink-400">Drop or click to browse</div>
        </>
      )}
    </div>
  );
}
