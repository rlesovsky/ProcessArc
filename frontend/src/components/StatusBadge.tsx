import { cn } from '@/lib/cn';

type Tone = 'ok' | 'warn' | 'danger' | 'neutral' | 'brand';

const TONES: Record<Tone, string> = {
  ok:      'bg-ok-50 text-ok-700 border-ok-500/30 dark:bg-ok-500/15 dark:text-ok-500 dark:border-ok-500/40',
  warn:    'bg-warn-50 text-warn-700 border-warn-500/30 dark:bg-warn-500/15 dark:text-warn-500 dark:border-warn-500/40',
  danger:  'bg-danger-50 text-danger-700 border-danger-500/30 dark:bg-danger-500/15 dark:text-danger-500 dark:border-danger-500/40',
  neutral: 'bg-ink-100 text-ink-700 border-ink-300 dark:bg-ink-700 dark:text-ink-200 dark:border-ink-600',
  brand:   'bg-brand-50 text-brand-700 border-brand-500/30 dark:bg-brand-500/15 dark:text-brand-100 dark:border-brand-500/40',
};

export function StatusBadge({ tone = 'neutral', children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium', TONES[tone])}>
      {children}
    </span>
  );
}
