import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, FileText, Folder, Package } from 'lucide-react';
import {
  isAtomicNode,
  isFolderNode,
  isInstanceNode,
  type IgnitionTagsBundle,
  type TreeNode,
} from '@/api/ignitionTags';

interface TagBundlePreviewProps {
  bundle: IgnitionTagsBundle;
  totalInstances: number;
}

export function TagBundlePreview({ bundle, totalInstances }: TagBundlePreviewProps) {
  // Collect every folder/instance key (paths) so Expand All can populate.
  const allKeys = useMemo(() => collectKeys(bundle, ''), [bundle]);
  const [open, setOpen] = useState<Set<string>>(() => new Set([keyFor(bundle, '')]));

  function toggle(key: string) {
    setOpen(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function expandAll() {
    setOpen(new Set(allKeys));
  }
  function collapseAll() {
    setOpen(new Set());
  }

  return (
    <section
      aria-label="Generated Tags"
      className="rounded-card border border-ink-200 bg-white dark:border-ink-700 dark:bg-ink-800"
    >
      <header className="flex items-center justify-between gap-2 border-b border-ink-200 px-4 py-3 dark:border-ink-700">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700 dark:text-ink-200">
            Generated Tags
          </h2>
          <span className="rounded-full bg-ink-100 px-2 py-0.5 text-[11px] font-medium text-ink-700 dark:bg-ink-700 dark:text-ink-200">
            {totalInstances} {totalInstances === 1 ? 'instance' : 'instances'}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={expandAll}
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-700"
          >
            Expand all
          </button>
          <button
            type="button"
            onClick={collapseAll}
            className="rounded-md px-2 py-1 text-ink-700 hover:bg-ink-100 dark:text-ink-200 dark:hover:bg-ink-700"
          >
            Collapse all
          </button>
        </div>
      </header>

      {/* Height flexes with the viewport: subtracts the chrome stack
          (header + tab bar + page heading + panel header + margins) so
          the tree grows to fill tall monitors and shrinks gracefully on
          short ones. min-h keeps it usable when the viewport is very
          short (e.g. split screens). */}
      <ul className="max-h-[calc(100vh-280px)] min-h-[280px] space-y-0.5 overflow-auto p-2 text-xs font-mono">
        <TreeNodeRow node={bundle} parentKey="" depth={0} open={open} onToggle={toggle} />
      </ul>
    </section>
  );
}

interface TreeNodeRowProps {
  node: TreeNode;
  parentKey: string;
  depth: number;
  open: Set<string>;
  onToggle: (key: string) => void;
}

function TreeNodeRow({ node, parentKey, depth, open, onToggle }: TreeNodeRowProps) {
  const key = keyFor(node, parentKey);

  if (isAtomicNode(node)) {
    return (
      <li>
        <Row
          depth={depth}
          icon={<FileText size={12} aria-hidden className="text-ink-400 dark:text-ink-500" />}
          label={
            <>
              <span className="text-ink-700 dark:text-ink-200">{node.name}</span>
              <span className="mx-1 text-ink-400 dark:text-ink-500">→</span>
              <span className="text-ink-500 dark:text-ink-400">{node.opcItemPath.binding}</span>
            </>
          }
        />
      </li>
    );
  }

  // Folder or UdtInstance — both have child `tags`.
  const isOpen = open.has(key);
  const children = node.tags;
  const folderIcon = isInstanceNode(node) ? (
    <Package size={12} aria-hidden className="text-ok-600 dark:text-ok-500" />
  ) : (
    <Folder
      size={12}
      aria-hidden
      className={
        depth === 0
          ? 'text-brand-600 dark:text-brand-100'
          : 'text-ink-500 dark:text-ink-400'
      }
    />
  );

  return (
    <li>
      <Row
        depth={depth}
        onToggle={() => onToggle(key)}
        isOpen={isOpen}
        hasChildren={children.length > 0}
        icon={folderIcon}
        label={
          isInstanceNode(node) ? (
            <>
              <span className="text-ink-700 dark:text-ink-200">{node.name}</span>
              <span className="ml-1 text-ink-500 dark:text-ink-400">({node.typeId})</span>
            </>
          ) : (
            <span className="text-ink-700 dark:text-ink-200">{node.name}/</span>
          )
        }
        trailing={
          isFolderNode(node) && depth === 0 ? (
            <span className="text-ink-500 dark:text-ink-400">
              root
            </span>
          ) : undefined
        }
      />
      {isOpen && (
        <ul>
          {children.map((child, i) => (
            <TreeNodeRow
              key={`${key}/${i}/${child.name}`}
              node={child}
              parentKey={`${key}/${i}`}
              depth={depth + 1}
              open={open}
              onToggle={onToggle}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

interface RowProps {
  depth: number;
  onToggle?: () => void;
  isOpen?: boolean;
  hasChildren?: boolean;
  icon: React.ReactNode;
  label: React.ReactNode;
  trailing?: React.ReactNode;
}

function Row({ depth, onToggle, isOpen, hasChildren, icon, label, trailing }: RowProps) {
  const handleClick = hasChildren && onToggle ? onToggle : undefined;
  const handleKey = handleClick
    ? (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }
    : undefined;
  return (
    <div
      role={handleClick ? 'button' : undefined}
      tabIndex={handleClick ? 0 : undefined}
      aria-expanded={hasChildren ? isOpen : undefined}
      onClick={handleClick}
      onKeyDown={handleKey}
      style={{ paddingLeft: depth * 16 }}
      className={
        handleClick
          ? 'flex items-center gap-1.5 rounded-md py-0.5 hover:bg-ink-100 dark:hover:bg-ink-700 cursor-pointer'
          : 'flex items-center gap-1.5 py-0.5'
      }
    >
      {hasChildren ? (
        isOpen ? (
          <ChevronDown size={12} aria-hidden className="text-ink-500" />
        ) : (
          <ChevronRight size={12} aria-hidden className="text-ink-500" />
        )
      ) : (
        <span aria-hidden className="inline-block w-3" />
      )}
      {icon}
      <span className="flex-1 truncate">{label}</span>
      {trailing}
    </div>
  );
}

function keyFor(node: TreeNode, parentKey: string): string {
  return `${parentKey}/${node.tagType}:${node.name}`;
}

function collectKeys(node: TreeNode, parentKey: string): string[] {
  const out: string[] = [];
  const key = keyFor(node, parentKey);
  if (!isAtomicNode(node)) {
    out.push(key);
    for (let i = 0; i < node.tags.length; i++) {
      out.push(...collectKeys(node.tags[i], `${key}/${i}`));
    }
  }
  return out;
}
