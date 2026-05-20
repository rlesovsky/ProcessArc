import { ApiKeySettings } from './ApiKeySettings';
import { ThemeToggle } from './ThemeToggle';

interface HeaderProps {
  projectName?: string;
  sourceFilename?: string;
  erpNumber?: string;
}

export function Header({ projectName, sourceFilename, erpNumber }: HeaderProps) {
  return (
    <header className="border-b border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-6 py-3">
        <div className="flex shrink-0 items-baseline gap-2">
          <span className="text-base font-semibold text-ink-900 dark:text-ink-50">ProcessArc</span>
          <span className="text-xs text-ink-500 dark:text-ink-400">UFP Phase 1</span>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap text-xs text-ink-500 dark:text-ink-400">
          {projectName && (
            <span className="truncate font-medium text-ink-700 dark:text-ink-200">{projectName}</span>
          )}
          {erpNumber && (
            <>
              <span aria-hidden>·</span>
              <span className="font-mono text-[11px] text-ink-600 dark:text-ink-300">#{erpNumber}</span>
            </>
          )}
          {sourceFilename && (
            <>
              <span aria-hidden className="hidden md:inline">·</span>
              <span className="hidden truncate font-mono text-[11px] md:inline">{sourceFilename}</span>
            </>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <ApiKeySettings />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
