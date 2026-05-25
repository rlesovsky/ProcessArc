import { ApiKeySettings } from './ApiKeySettings';
import { ThemeToggle } from './ThemeToggle';
import { container } from '@/lib/layout';
import logo from '@/assets/processarc-logo-light.png';

interface HeaderProps {
  projectName?: string;
  sourceFilename?: string;
  erpNumber?: string;
}

export function Header({ projectName, sourceFilename, erpNumber }: HeaderProps) {
  return (
    <header className="border-b border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-850">
      <div className={`${container} flex items-center gap-3 py-1 sm:gap-4`}>
        <div className="flex shrink-0 items-center gap-3 px-2 sm:gap-4">
          {/* Single transparent (RGBA) logo asset used in both themes.
              Sized to fit the compact ~56px header band with breathing
              room. Width auto-fits to preserve the wordmark's aspect ratio. */}
          <img
            src={logo}
            alt="ProcessArc"
            className="block w-auto"
            style={{ height: 'clamp(2.25rem, 3.3vw, 3rem)' }}
          />
          {/* Subtitle hidden on phones — the logo alone identifies the app. */}
          <span className="hidden text-[11px] uppercase tracking-wide text-ink-500 dark:text-ink-400 sm:inline">
            UFP Phase 1
          </span>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap text-xs text-ink-500 dark:text-ink-400">
          {projectName && (
            <span className="truncate font-medium text-ink-900 dark:text-ink-100">{projectName}</span>
          )}
          {erpNumber && (
            <>
              <span aria-hidden>·</span>
              <span className="font-mono text-[11px] text-ink-700 dark:text-ink-300">#{erpNumber}</span>
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
