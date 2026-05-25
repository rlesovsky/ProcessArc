/**
 * Phase 3b spec §8 — frontend tests for the Ignition Tag Builder tab
 * and its tab-nav scaffolding. Numbered 1-10 to match the spec list.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import App from '@/App';
import {
  installFetchMock,
  makeFakeSuccessEnvelope,
  makeFakeXlsx,
} from './helpers';
import type { IgnitionTagsBundle, ValidationReport } from '@/api/ignitionTags';

let mock: ReturnType<typeof installFetchMock>;

beforeEach(() => {
  mock = installFetchMock();
  // Clear any URL query string from a prior test.
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  mock.restore();
});

function withBundleResponse(
  bundle: IgnitionTagsBundle,
  report: ValidationReport = { errors: [], warnings: [] },
): void {
  mock.add({
    match: (url, init) =>
      url.includes('/api/ignition-tags/build') && init?.method === 'POST',
    respond: async () => {
      const envelope = makeFakeSuccessEnvelope(bundle, report);
      return new Response(JSON.stringify(envelope), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  });
}

function withValidationError(payload: { error: string; report: ValidationReport }) {
  mock.add({
    match: (url, init) =>
      url.includes('/api/ignition-tags/build') && init?.method === 'POST',
    respond: async () =>
      new Response(
        JSON.stringify({ error: payload.error, validation_report: payload.report }),
        { status: 400, headers: { 'Content-Type': 'application/json' } },
      ),
  });
}

function withServerError() {
  mock.add({
    match: (url, init) =>
      url.includes('/api/ignition-tags/build') && init?.method === 'POST',
    respond: async () => new Response('', { status: 500 }),
  });
}

// Rooted folder tree matching the Ignition import format. Mirrors the
// shape `build_ignition_tree(instances)` produces for one instance:
// site → sys_name → sys_num → folder → UdtInstance.
const SAMPLE_BUNDLE: IgnitionTagsBundle = {
  name: 'UFP_Athens',
  tagType: 'Folder',
  tags: [
    {
      name: 'A1',
      tagType: 'Folder',
      tags: [
        {
          name: '01',
          tagType: 'Folder',
          tags: [
            {
              name: 'LevelSensors',
              tagType: 'Folder',
              tags: [
                {
                  name: 'Tank 1',
                  typeId: 'Tank/Tank Level Sensors',
                  tagType: 'UdtInstance',
                  tags: [
                    {
                      name: 'Raw Min',
                      tagType: 'AtomicTag',
                      opcItemPath: { bindType: 'parameter', binding: 'ns=1;s=[{plc}]500' },
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
  ],
};

async function selectIgnitionTagsTab() {
  const tagsTab = screen.getByRole('tab', { name: /Ignition Tag Builder/i });
  await userEvent.click(tagsTab);
}

async function pickFile(file: File) {
  const input = screen.getByTestId('ignition-tags-file-input') as HTMLInputElement;
  // userEvent.upload doesn't reliably fire on a display:none input; use
  // fireEvent.change directly so the controlled handler runs.
  fireEvent.change(input, { target: { files: [file] } });
}

async function uploadAndBuild(file: File) {
  await selectIgnitionTagsTab();
  await pickFile(file);
  const buildBtn = await screen.findByRole('button', { name: /Build Tags/i });
  await waitFor(() => expect(buildBtn).not.toBeDisabled());
  await userEvent.click(buildBtn);
}

// ---------------------------------------------------------------------------
// 1. Tab nav default
// ---------------------------------------------------------------------------

describe('1. Tab nav default', () => {
  it('mounts with Project Wizard active and Tag Builder inactive', () => {
    render(<App />);
    const wizardTab = screen.getByRole('tab', { name: /Project Wizard/i });
    const tagsTab = screen.getByRole('tab', { name: /Ignition Tag Builder/i });
    expect(wizardTab).toHaveAttribute('aria-selected', 'true');
    expect(tagsTab).toHaveAttribute('aria-selected', 'false');
  });
});

// ---------------------------------------------------------------------------
// 2. Tab switching preserves wizard state
// ---------------------------------------------------------------------------

describe('2. Tab switching preserves wizard state', () => {
  it('keeps the project-name input value across a switch round-trip', async () => {
    const user = userEvent.setup();
    render(<App />);

    const nameInput = screen.getByLabelText(/Project name/i) as HTMLInputElement;
    await user.type(nameInput, 'Hampton FY26');
    expect(nameInput.value).toBe('Hampton FY26');

    // Switch away…
    await user.click(screen.getByRole('tab', { name: /Ignition Tag Builder/i }));
    // …and back.
    await user.click(screen.getByRole('tab', { name: /Project Wizard/i }));

    const nameInputAgain = screen.getByLabelText(/Project name/i) as HTMLInputElement;
    expect(nameInputAgain.value).toBe('Hampton FY26');
  });
});

// ---------------------------------------------------------------------------
// 3. Tab switching preserves Tag Builder state
// ---------------------------------------------------------------------------

describe('3. Tab switching preserves Tag Builder state', () => {
  it('keeps Results state visible after switching tabs', async () => {
    withBundleResponse(SAMPLE_BUNDLE);
    render(<App />);

    await uploadAndBuild(makeFakeXlsx());
    await screen.findByRole('region', { name: /Generated Tags/i }, { timeout: 3000 });
    expect((await screen.findAllByText(/1 instance/)).length).toBeGreaterThan(0);

    // Switch away.
    await userEvent.click(screen.getByRole('tab', { name: /Project Wizard/i }));
    // The results panel is still mounted, just hidden — assert that.
    const tagsPanel = document.getElementById('tabpanel-ignition-tags');
    expect(tagsPanel?.classList.contains('hidden')).toBe(true);
    expect(tagsPanel?.getAttribute('aria-hidden')).toBe('true');
    // Switch back.
    await userEvent.click(screen.getByRole('tab', { name: /Ignition Tag Builder/i }));
    expect((await screen.findAllByText(/1 instance/)).length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Upload → Results happy path
// ---------------------------------------------------------------------------

describe('4. Upload → Results happy path', () => {
  it('renders Results with the instance count and "No issues found."', async () => {
    withBundleResponse(SAMPLE_BUNDLE);
    render(<App />);

    await uploadAndBuild(makeFakeXlsx());

    // Wait up to 3s — the JSZip parse happens off the main thread.
    await screen.findByRole('region', { name: /Generated Tags/i }, { timeout: 3000 });
    const matches = await screen.findAllByText(/1 instance/);
    expect(matches.length).toBeGreaterThan(0);
    expect(screen.getByText(/No issues found\./)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 5. Upload → Results with warnings
// ---------------------------------------------------------------------------

describe('5. Upload → Results with warnings', () => {
  it('renders the warnings panel with sheet/row refs for each warning', async () => {
    const report: ValidationReport = {
      errors: [],
      warnings: [
        {
          severity: 'warning',
          code: 'row.no_tags',
          message: 'Row for instance "Tank 9" has every tag column blank.',
          sheet: 'Tank Level Sensors',
          row: 5,
        },
        {
          severity: 'warning',
          code: 'duplicate_instance',
          message: 'Duplicate UDT instance path [Athens]UFP_Athens/A1/01/LevelSensors/Tank 1.',
          sheet: 'Tank Level Sensors',
          row: 2,
        },
      ],
    };
    withBundleResponse(SAMPLE_BUNDLE, report);
    render(<App />);

    await uploadAndBuild(makeFakeXlsx());

    const panel = await screen.findByRole('region', { name: /Validation Report/i });
    const inPanel = within(panel);
    expect(inPanel.getByText(/Warnings/i)).toBeInTheDocument();
    expect(inPanel.getByText(/row.no_tags/)).toBeInTheDocument();
    expect(inPanel.getByText(/duplicate_instance/)).toBeInTheDocument();
    expect(inPanel.getByText(/sheet Tank Level Sensors · row 5/)).toBeInTheDocument();
    expect(inPanel.getByText(/sheet Tank Level Sensors · row 2/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 6. Upload → 400 error path
// ---------------------------------------------------------------------------

describe('6. Upload → 400 error path', () => {
  it('renders Error state with the validation report and "Upload another file"', async () => {
    withValidationError({
      error: 'Workbook failed validation.',
      report: {
        errors: [
          {
            severity: 'error',
            code: 'header.missing_provider',
            message: 'Sheet 0 cell B2 (tag provider) is blank.',
            sheet: 'Header',
            row: 2,
            column: 'B',
          },
        ],
        warnings: [],
      },
    });
    render(<App />);

    await uploadAndBuild(makeFakeXlsx());

    expect(await screen.findByRole('heading', { name: /Couldn't build the bundle/i })).toBeInTheDocument();
    const panel = await screen.findByRole('region', { name: /Validation Report/i });
    expect(within(panel).getByText(/header.missing_provider/)).toBeInTheDocument();
    expect(within(panel).getByText(/Sheet 0 cell B2 \(tag provider\) is blank\./)).toBeInTheDocument();

    // Action button returns to Upload.
    const again = screen.getByRole('button', { name: /Upload another file/i });
    await userEvent.click(again);
    expect(
      screen.getByRole('button', { name: /Build Tags/i }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 7. Upload → 5xx generic error
// ---------------------------------------------------------------------------

describe('7. Upload → 5xx generic error', () => {
  it('shows only the generic message — no validation panel', async () => {
    withServerError();
    render(<App />);

    await uploadAndBuild(makeFakeXlsx());

    expect(await screen.findByRole('heading', { name: /Couldn't build the bundle/i })).toBeInTheDocument();
    expect(screen.getByText(/The server couldn't process this file/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: /Validation Report/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 8. File-extension client-side guard
// ---------------------------------------------------------------------------

describe('8. File-extension client-side guard', () => {
  it('rejects a .txt file inline and never POSTs', async () => {
    render(<App />);

    await selectIgnitionTagsTab();

    const input = screen.getByTestId('ignition-tags-file-input') as HTMLInputElement;
    const bad = new File(['hello'], 'notes.txt', { type: 'text/plain' });
    fireEvent.change(input, { target: { files: [bad] } });

    expect(screen.getByRole('alert')).toHaveTextContent(/Only \.xlsx files are supported\./);
    // Build button stays disabled — no file is selected.
    expect(screen.getByRole('button', { name: /Build Tags/i })).toBeDisabled();
    // Fetch was never called for the build endpoint.
    const postCalls = (mock.spy.mock.calls as Array<[unknown, RequestInit | undefined]>).filter(
      ([url, init]) => String(url).includes('/api/ignition-tags/build') && init?.method === 'POST',
    );
    expect(postCalls).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 9. Download button delivers the bundle as JSON
// ---------------------------------------------------------------------------

describe('9. Download button delivers the bundle as JSON', () => {
  it('writes the bundle dict (only) to a .json file', async () => {
    const captured: Blob[] = [];
    const originalCreate = URL.createObjectURL;
    URL.createObjectURL = ((blob: Blob) => {
      captured.push(blob);
      return 'blob:mock';
    }) as typeof URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.revokeObjectURL = (() => undefined) as typeof URL.revokeObjectURL;

    try {
      withBundleResponse(SAMPLE_BUNDLE);
      render(<App />);

      await uploadAndBuild(makeFakeXlsx());
      await screen.findByRole('region', { name: /Generated Tags/i });
      expect((await screen.findAllByText(/1 instance/)).length).toBeGreaterThan(0);

      const dl = screen.getByRole('button', { name: /Download JSON/i });
      await userEvent.click(dl);

      expect(captured).toHaveLength(1);
      // application/json blob, parseable, equals the original bundle —
      // no envelope wrapping, no metadata fields.
      expect(captured[0].type).toBe('application/json');
      const text = await captured[0].text();
      expect(JSON.parse(text)).toEqual(SAMPLE_BUNDLE);
    } finally {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    }
  });
});

// ---------------------------------------------------------------------------
// 10. Placeholder cleanup
// ---------------------------------------------------------------------------

describe('10. Placeholder cleanup', () => {
  it('does not render any "Coming in Phase 3b" placeholder for ?view=ignition-tags', async () => {
    window.history.replaceState(null, '', '/?view=ignition-tags');
    render(<App />);

    // No placeholder text anywhere.
    expect(screen.queryByText(/Coming in Phase 3b/i)).not.toBeInTheDocument();
    // The Project Wizard remains the active tab.
    expect(screen.getByRole('tab', { name: /Project Wizard/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });
});

// ---------------------------------------------------------------------------
// Tiny suspicious-state guard: the "Build Tags" button is disabled until
// a valid file is picked (covers the busy → enabled state machine).
// ---------------------------------------------------------------------------

describe('Build Tags button gating', () => {
  it('is disabled until a file is selected and re-enabled after upload', async () => {
    render(<App />);
    await selectIgnitionTagsTab();
    const btn = screen.getByRole('button', { name: /Build Tags/i });
    expect(btn).toBeDisabled();

    await pickFile(makeFakeXlsx());

    await waitFor(() => expect(btn).not.toBeDisabled());
  });
});
