import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, XCircle } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { ValidationIssue, ValidationReport } from '@/api/ignitionTags';

interface ValidationReportPanelProps {
  report: ValidationReport;
  /** When true (error state), always render the Errors section first. */
  errorsOnTop?: boolean;
}

export function ValidationReportPanel({ report }: ValidationReportPanelProps) {
  const hasErrors = report.errors.length > 0;
  const hasWarnings = report.warnings.length > 0;
  const clean = !hasErrors && !hasWarnings;

  return (
    <section
      aria-label="Validation Report"
      className="rounded-card border border-ink-200 bg-white p-4 dark:border-ink-700 dark:bg-ink-800"
    >
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-700 dark:text-ink-200">
        Validation Report
      </h2>

      {clean && (
        <div className="flex items-center gap-2 text-sm text-ok-700 dark:text-ok-500">
          <CheckCircle2 size={18} aria-hidden />
          <span>No issues found.</span>
        </div>
      )}

      {hasErrors && (
        <IssueSection
          title="Errors"
          tone="error"
          issues={sortIssues(report.errors)}
        />
      )}
      {hasWarnings && (
        <IssueSection
          title="Warnings"
          tone="warning"
          issues={sortIssues(report.warnings)}
        />
      )}
    </section>
  );
}

function sortIssues(issues: ValidationIssue[]): ValidationIssue[] {
  return [...issues].sort((a, b) => {
    const sheetCmp = (a.sheet ?? '').localeCompare(b.sheet ?? '');
    if (sheetCmp !== 0) return sheetCmp;
    return (a.row ?? 0) - (b.row ?? 0);
  });
}

interface IssueSectionProps {
  title: string;
  tone: 'error' | 'warning';
  issues: ValidationIssue[];
}

function IssueSection({ title, tone, issues }: IssueSectionProps) {
  const [open, setOpen] = useState(true);
  const Icon = tone === 'error' ? XCircle : AlertTriangle;
  const headingTone =
    tone === 'error'
      ? 'text-danger-700 dark:text-danger-500'
      : 'text-warn-700 dark:text-warn-500';
  const badgeTone =
    tone === 'error'
      ? 'bg-danger-50 text-danger-700 dark:bg-danger-500/10 dark:text-danger-500'
      : 'bg-warn-50 text-warn-700 dark:bg-warn-500/10 dark:text-warn-500';

  return (
    <div className="mt-3 first:mt-0">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-md py-1 text-left text-sm hover:bg-ink-100 dark:hover:bg-ink-700"
      >
        {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
        <Icon size={14} aria-hidden className={headingTone} />
        <span className={cn('font-medium', headingTone)}>{title}</span>
        <span className={cn('rounded-full px-2 py-0.5 text-[11px] font-medium', badgeTone)}>
          {issues.length}
        </span>
      </button>
      {open && (
        <ul className="mt-2 space-y-1 pl-6">
          {issues.map((issue, i) => (
            <li
              key={`${issue.code}-${i}`}
              className="rounded-md border border-ink-200 px-2 py-1.5 text-xs text-ink-700 dark:border-ink-700 dark:text-ink-200"
            >
              <div>{issue.message}</div>
              {locationText(issue) && (
                <div className="mt-0.5 font-mono text-[11px] text-ink-500 dark:text-ink-400">
                  {locationText(issue)}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function locationText(issue: ValidationIssue): string | null {
  const parts: string[] = [];
  if (issue.sheet) parts.push(`sheet ${issue.sheet}`);
  if (issue.row != null) parts.push(`row ${issue.row}`);
  if (issue.column) parts.push(`column ${issue.column}`);
  parts.push(`code ${issue.code}`);
  return parts.join(' · ');
}
