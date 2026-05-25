import { cn } from '@/lib/cn';
import { container } from '@/lib/layout';

export interface TabDef<Id extends string> {
  id: Id;
  label: string;
}

interface TabBarProps<Id extends string> {
  tabs: ReadonlyArray<TabDef<Id>>;
  activeId: Id;
  onSelect: (id: Id) => void;
}

// Generic, label-driven tab bar. Future top-level features land as new
// entries in the `tabs` array — no JSX changes needed here.
export function TabBar<Id extends string>({ tabs, activeId, onSelect }: TabBarProps<Id>) {
  return (
    <nav
      aria-label="Top-level features"
      className="border-b border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800"
    >
      <div
        role="tablist"
        className={`${container} flex gap-1`}
      >
        {tabs.map((tab) => {
          const active = tab.id === activeId;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`tabpanel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onSelect(tab.id)}
              className={cn(
                'relative -mb-px px-3 py-2.5 text-sm transition-colors sm:px-4',
                // Active tab underline is the logo's green (ok-500) in both
                // themes, per the theme spec §3.3 — visually echoes the
                // green arc accent in the logo.
                active
                  ? 'border-b-2 border-ok-500 font-medium text-ink-900 dark:text-ink-50'
                  : 'border-b-2 border-transparent text-ink-500 hover:text-ink-900 dark:text-ink-400 dark:hover:text-ink-50',
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
