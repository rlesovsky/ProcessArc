import { vi, type MockInstance } from 'vitest';
import type { IgnitionTagsBundle, TreeNode, ValidationReport } from '@/api/ignitionTags';

/**
 * Build the JSON envelope the backend returns on success — the same
 * shape `buildIgnitionTags` parses out of `response.json()`.
 *
 * `bundle` must be a rooted folder tree (matches Ignition's import
 * format), not the old flat-map shape.
 */
export function makeFakeSuccessEnvelope(
  bundle: IgnitionTagsBundle,
  report: ValidationReport = { errors: [], warnings: [] },
  site = 'UFP_Test',
): {
  bundle: IgnitionTagsBundle;
  validation_report: ValidationReport;
  site: string;
  instance_count: number;
} {
  return {
    bundle,
    validation_report: report,
    site,
    instance_count: countInstances(bundle),
  };
}

function countInstances(node: TreeNode): number {
  if (node.tagType === 'UdtInstance') return 1;
  if (node.tagType === 'AtomicTag') return 0;
  return node.tags.reduce((n, c) => n + countInstances(c), 0);
}

interface FetchHandler {
  match: (url: string, init?: RequestInit) => boolean;
  respond: () => Response | Promise<Response>;
}

/**
 * Install a global fetch mock with a per-URL handler chain. Last-added
 * handler wins (so tests can override defaults). Returns a teardown.
 *
 * Default behavior: GET /settings/api-key → {configured:false} 200.
 * This is what ApiKeySettings calls on mount; without it the test
 * console fills up with unhandled fetch warnings.
 */
export function installFetchMock(): {
  add: (h: FetchHandler) => void;
  spy: MockInstance;
  restore: () => void;
} {
  const handlers: FetchHandler[] = [
    {
      match: (url, init) =>
        url.includes('/settings/api-key') && (!init || init.method === undefined),
      respond: () =>
        new Response(JSON.stringify({ configured: false, masked: null }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    },
  ];

  const spy = vi.spyOn(global, 'fetch').mockImplementation(
    async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      for (let i = handlers.length - 1; i >= 0; i--) {
        if (handlers[i].match(url, init)) {
          return handlers[i].respond();
        }
      }
      throw new Error(`No fetch mock handler for ${init?.method ?? 'GET'} ${url}`);
    },
  ) as unknown as MockInstance;

  return {
    add: (h) => handlers.push(h),
    spy,
    restore: () => spy.mockRestore(),
  };
}

/**
 * Build a File the upload picker can accept. The vitest jsdom
 * environment provides File, so this is just a thin wrapper that
 * matches the .xlsx mime + extension the client guards on.
 */
export function makeFakeXlsx(
  name = 'template.xlsx',
  size = 1024,
): File {
  const bytes = new Uint8Array(size).fill(1);
  return new File([bytes], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}
