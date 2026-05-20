import { ApiKeySettings } from './ApiKeySettings';
import { ThemeToggle } from './ThemeToggle';

interface HeaderProps {
  projectName?: string;
  sourceFilename?: string;
  erpNumber?: string;
}

export function Header({ projectName, sourceFilename, erpNumber }: HeaderProps) {
  return (
    // The header band stays dark navy in both themes — the ProcessArc logo
    // has a built-in navy background, so a permanent dark band keeps the
    // logo edge invisible regardless of light/dark mode.
    <header className="border-b border-ink-800 bg-ink-900">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-4 px-6 py-2">
        <div className="flex shrink-0 items-center gap-3">
          <img
            src="/processarc-logo.png"
            alt="ProcessArc"
            className="h-9 w-auto"
            // Width hint for the browser so layout doesn't jump while the
            // image loads. The actual rendered width follows h-9 + aspect.
            width={144}
            height={36}
          />
          <span className="text-[11px] uppercase tracking-wide text-ink-400">UFP Phase 1</span>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-3 overflow-hidden whitespace-nowrap text-xs text-ink-400">
          {projectName && (
            <span className="truncate font-medium text-ink-100">{projectName}</span>
          )}
          {erpNumber && (
            <>
              <span aria-hidden>·</span>
              <span className="font-mono text-[11px] text-ink-300">#{erpNumber}</span>
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
