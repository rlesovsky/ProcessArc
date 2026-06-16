// API client for the Commissioning Workbook Builder.
//
// Single endpoint: POST /api/commissioning-workbook/build
//   multipart upload of a customer write-up xlsx; response is the
//   populated workbook as a Blob, plus a structured BuildReport
//   returned in the X-Build-Report header (base64-JSON) so the UI can
//   render the change log alongside the download button.

export interface ChangeLogEntry {
  sheet: string;
  cell: string;
  before: string;
  after: string;
  reason: string;
  conflict: boolean;
}

export interface BuildReport {
  template_name: string;
  source_sheets_seen: string[];
  changes: ChangeLogEntry[];
  flow_meters_matched: number;
  sequence_notes_attached: number;
  graphic_notes_attached: number;
  plant_facts_attached: number;
  warnings: string[];
}

export interface BuildSuccess {
  ok: true;
  blob: Blob;
  filename: string;
  report: BuildReport;
}

export interface BuildFailure {
  ok: false;
  status: number;
  message: string;
}

export type BuildResult = BuildSuccess | BuildFailure;

/** Decode the X-Build-Report header (base64 JSON). Returns null on failure
 *  so a malformed header doesn't tank the download itself. */
function decodeBuildReport(headerValue: string | null): BuildReport | null {
  if (!headerValue) return null;
  try {
    // atob handles base64 → binary string; then decodeURIComponent of
    // each char turns it into proper UTF-8 (this is the standard
    // "atob + utf-8" trick because atob itself doesn't know about UTF-8).
    const binary = atob(headerValue);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    const text = new TextDecoder('utf-8').decode(bytes);
    return JSON.parse(text) as BuildReport;
  } catch {
    return null;
  }
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const m = header.match(/filename="?([^";]+)"?/i);
  return m ? m[1] : null;
}

export async function buildCommissioningWorkbook(
  source: File,
): Promise<BuildResult> {
  const form = new FormData();
  form.append('source', source);
  const resp = await fetch('/api/commissioning-workbook/build', {
    method: 'POST',
    body: form,
  });
  if (!resp.ok) {
    let message = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // body wasn't JSON — keep the default message
    }
    return { ok: false, status: resp.status, message };
  }
  const blob = await resp.blob();
  const filename =
    filenameFromContentDisposition(resp.headers.get('content-disposition')) ??
    'commissioning_workbook_filled.xlsx';
  // Fallback BuildReport in case the header is missing — the download
  // still works, just without the change-log panel.
  const report = decodeBuildReport(resp.headers.get('x-build-report')) ?? {
    template_name: '',
    source_sheets_seen: [],
    changes: [],
    flow_meters_matched: 0,
    sequence_notes_attached: 0,
    graphic_notes_attached: 0,
    plant_facts_attached: 0,
    warnings: [],
  };
  return { ok: true, blob, filename, report };
}

/** Trigger a browser download of the result. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
