// Client for POST /api/ignition-tags/build (Phase 3a backend).
//
// On success the backend returns a small JSON envelope:
//   { bundle, validation_report, site, instance_count }
// — `bundle` is the data the engineer downloads (one flat JSON file),
// `validation_report` populates the side panel in the Results view.
//
// The download button writes only the `bundle` field to disk so the
// downloaded file is a pure Ignition-importable JSON object, not a
// metadata-wrapped envelope.

// =============================================================================
// Shared types — mirror backend/features/ignition_tags/schema.py
// =============================================================================

export interface OpcItemPath {
  bindType: 'parameter';
  binding: string;
}

export interface AtomicTag {
  name: string;
  tagType: 'AtomicTag';
  opcItemPath: OpcItemPath;
}

export interface FolderTag {
  name: string;
  tagType: 'Folder';
  tags: TreeNode[];
}

export interface InstanceConfig {
  name: string;
  typeId: string;
  tagType: 'UdtInstance';
  tags: TreeNode[];
}

/** Any node in the Ignition-importable folder tree. */
export type TreeNode = AtomicTag | FolderTag | InstanceConfig;

export function isFolderNode(node: TreeNode): node is FolderTag {
  return node.tagType === 'Folder';
}
export function isInstanceNode(node: TreeNode): node is InstanceConfig {
  return node.tagType === 'UdtInstance';
}
export function isAtomicNode(node: TreeNode): node is AtomicTag {
  return node.tagType === 'AtomicTag';
}

/** A rooted folder tree — the `bundle` field of the API response and
 *  the JSON the user downloads. Matches what Ignition Designer's Tag
 *  Browser Import expects. */
export type IgnitionTagsBundle = FolderTag;

export interface ValidationIssue {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  sheet?: string | null;
  row?: number | null;
  column?: string | null;
}

export interface ValidationReport {
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

// =============================================================================
// Result types — what the frontend gets back from the client
// =============================================================================

export interface BuildIgnitionTagsSuccess {
  ok: true;
  /** Just the bundle, ready to download as a single .json file. */
  bundle: IgnitionTagsBundle;
  /** Suggested download filename ("ignition_tags_<site>_<ts>.json"). */
  filename: string;
  /** Warnings (errors are empty on a 200). */
  report: ValidationReport;
  /** Total instance count across all base paths. */
  instanceCount: number;
}

export interface BuildIgnitionTagsValidationError {
  ok: false;
  kind: 'validation';
  message: string;
  report: ValidationReport;
}

export interface BuildIgnitionTagsGenericError {
  ok: false;
  kind: 'generic';
  message: string;
}

export type BuildIgnitionTagsResult =
  | BuildIgnitionTagsSuccess
  | BuildIgnitionTagsValidationError
  | BuildIgnitionTagsGenericError;

// =============================================================================
// Implementation
// =============================================================================

const GENERIC_ERROR_MESSAGE =
  "The server couldn't process this file. Try again, and if it keeps failing, check that the backend is running.";

interface SuccessEnvelope {
  bundle: IgnitionTagsBundle;
  validation_report: ValidationReport;
  site: string | null;
  instance_count: number;
}

function buildFilename(site: string | null): string {
  const safe = (site ?? 'site')
    .split('')
    .map(c => (/[A-Za-z0-9_-]/.test(c) ? c : '_'))
    .join('')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || 'site';
  // YYYYMMDDTHHmmssZ — keep it filesystem-safe and sortable.
  const ts = new Date().toISOString().replace(/[-:]/g, '').replace(/\..*$/, 'Z');
  return `ignition_tags_${safe}_${ts}.json`;
}

function instanceCount(bundle: IgnitionTagsBundle): number {
  let total = 0;
  for (const list of Object.values(bundle)) total += list.length;
  return total;
}

export async function buildIgnitionTags(
  file: File,
  fetchImpl: typeof fetch = fetch,
): Promise<BuildIgnitionTagsResult> {
  const form = new FormData();
  form.append('file', file);

  let response: Response;
  try {
    response = await fetchImpl('/api/ignition-tags/build', {
      method: 'POST',
      body: form,
    });
  } catch {
    return { ok: false, kind: 'generic', message: GENERIC_ERROR_MESSAGE };
  }

  if (response.status === 200) {
    let envelope: SuccessEnvelope;
    try {
      envelope = (await response.json()) as SuccessEnvelope;
    } catch (e) {
      return {
        ok: false,
        kind: 'generic',
        message: `The server returned a malformed response: ${(e as Error).message}`,
      };
    }
    return {
      ok: true,
      bundle: envelope.bundle,
      report: envelope.validation_report,
      instanceCount: envelope.instance_count,
      filename: buildFilename(envelope.site),
    };
  }

  if (response.status === 400) {
    try {
      const body = (await response.json()) as {
        error?: string;
        validation_report?: ValidationReport;
      };
      if (body.validation_report) {
        return {
          ok: false,
          kind: 'validation',
          message: body.error ?? 'Workbook failed validation.',
          report: body.validation_report,
        };
      }
    } catch {
      // fall through to generic
    }
    return { ok: false, kind: 'generic', message: GENERIC_ERROR_MESSAGE };
  }

  return { ok: false, kind: 'generic', message: GENERIC_ERROR_MESSAGE };
}

export const ignitionTagsApi = {
  build: buildIgnitionTags,
  instanceCount,
};

/**
 * Serialize the bundle to a pretty-printed JSON Blob. The download
 * button writes this directly to disk — no wrapping, no metadata. The
 * resulting file is a flat `{ "<base_path>": [instance, ...] }` map
 * the engineer can feed into Ignition Designer or a `system.tag.configure`
 * script unchanged.
 */
export function bundleAsJsonBlob(bundle: IgnitionTagsBundle): Blob {
  return new Blob([JSON.stringify(bundle, null, 2) + '\n'], {
    type: 'application/json',
  });
}
