import { Check } from 'lucide-react';
import { cn } from '@/lib/cn';
import { container } from '@/lib/layout';
import type { PipelineStage } from '@/api/types';

const STEPS: Array<{ stage: PipelineStage; label: string }> = [
  { stage: 'configure', label: 'Configure' },
  { stage: 'discover',  label: 'Discover' },
  { stage: 'extract',   label: 'Extract' },
  { stage: 'review',    label: 'Review' },
  { stage: 'export',    label: 'Export' },
];

interface StepBarProps {
  activeStage: PipelineStage;
  completedStages: PipelineStage[];
  onJumpTo?: (stage: PipelineStage) => void;
}

const stageIndex = (s: PipelineStage) => STEPS.findIndex(x => x.stage === s);

export function StepBar({ activeStage, completedStages, onJumpTo }: StepBarProps) {
  const activeIdx = stageIndex(activeStage);

  return (
    <nav
      aria-label="Pipeline steps"
      className="border-b border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800"
    >
      <ol className={`${container} flex items-center gap-0.5 overflow-x-auto py-2 sm:gap-1`}>
        {STEPS.map((step, i) => {
          const done = completedStages.includes(step.stage);
          const active = step.stage === activeStage;
          const canJump = done && i <= activeIdx && onJumpTo;
          return (
            <li key={step.stage} className="flex shrink-0 items-center">
              <button
                type="button"
                disabled={!canJump}
                onClick={() => canJump && onJumpTo(step.stage)}
                aria-label={step.label}
                className={cn(
                  'group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm sm:px-3',
                  active && 'border-2 border-brand-500 font-medium text-brand-700 dark:text-brand-100',
                  !active && done && 'text-ink-700 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-700',
                  !active && !done && 'text-ink-500 cursor-default dark:text-ink-400',
                  canJump && 'cursor-pointer',
                )}
              >
                <span
                  className={cn(
                    'inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-medium',
                    active && 'bg-brand-500 text-white',
                    !active && done && 'bg-ok-500 text-white',
                    !active && !done && 'bg-ink-200 text-ink-500 dark:bg-ink-700 dark:text-ink-400',
                  )}
                  aria-hidden
                >
                  {done && !active ? <Check size={12} strokeWidth={3} /> : i + 1}
                </span>
                {/* Label hides on the smallest screens where the numbered
                    circle alone identifies the step. The aria-label keeps
                    screen-reader users covered. */}
                <span className="hidden sm:inline">{step.label}</span>
              </button>
              {i < STEPS.length - 1 && (
                <span className="mx-0.5 h-px w-3 bg-ink-200 dark:bg-ink-700 sm:mx-1 sm:w-6" aria-hidden />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
