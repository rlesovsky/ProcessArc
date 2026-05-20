import { cn } from '@/lib/cn';

interface FooterNavProps {
  canBack: boolean;
  canContinue: boolean;
  continueLabel?: string;
  busy?: boolean;
  onBack?: () => void;
  onContinue?: () => void;
}

export function FooterNav({
  canBack, canContinue, continueLabel = 'Continue', busy,
  onBack, onContinue,
}: FooterNavProps) {
  return (
    <footer className="border-t border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800">
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8 2xl:max-w-[1440px]">
        <button
          type="button"
          disabled={!canBack}
          onClick={onBack}
          className={cn(
            'rounded-md px-3 py-1.5 text-sm',
            canBack
              ? 'text-ink-700 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-700'
              : 'cursor-not-allowed text-ink-300 dark:text-ink-600',
          )}
        >
          ← Back
        </button>
        <button
          type="button"
          disabled={!canContinue || busy}
          onClick={onContinue}
          className={cn(
            'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
            canContinue && !busy
              ? 'bg-brand-500 text-white hover:bg-brand-600'
              : 'cursor-not-allowed bg-ink-200 text-ink-500 dark:bg-ink-700 dark:text-ink-400',
          )}
        >
          {busy ? 'Working…' : `${continueLabel} →`}
        </button>
      </div>
    </footer>
  );
}
