import type {
  ApiKeyStatus,
  ConfirmResponse,
  CreateProjectResponse,
  DeviceModel,
  DeviceModelSaveResponse,
  ExportResult,
  ExtractState,
  HealthResponse,
  PlantConfiguration,
} from './types';

export interface ExtractStartOptions {
  dryRun?: boolean;
  simulateFailureSheet?: string | null;
}

function extractQuery(opts: ExtractStartOptions = {}): string {
  const params = new URLSearchParams();
  if (opts.dryRun) params.set('dry_run', 'true');
  if (opts.simulateFailureSheet) params.set('simulate_failure_sheet', opts.simulateFailureSheet);
  const s = params.toString();
  return s ? `?${s}` : '';
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

async function unwrap<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  async health(): Promise<HealthResponse> {
    return unwrap(await fetch('/health'));
  },

  async createProject(input: {
    sequenceWorkbook: File;
    ioTemplate: File;
    ceProfile?: File | null;
    projectName?: string;
  }): Promise<CreateProjectResponse> {
    const form = new FormData();
    form.append('sequence_workbook', input.sequenceWorkbook);
    form.append('io_template', input.ioTemplate);
    if (input.ceProfile) form.append('ce_profile', input.ceProfile);
    if (input.projectName) form.append('project_name', input.projectName);
    return unwrap(await fetch('/projects', { method: 'POST', body: form }));
  },

  async getPlantConfiguration(projectId: string): Promise<PlantConfiguration> {
    return unwrap(await fetch(`/projects/${projectId}/plant-configuration`));
  },

  async confirmPlantConfiguration(
    projectId: string,
    plant: PlantConfiguration,
  ): Promise<ConfirmResponse> {
    return unwrap(
      await fetch(`/projects/${projectId}/plant-configuration/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(plant),
      }),
    );
  },

  async getApiKeyStatus(): Promise<ApiKeyStatus> {
    return unwrap(await fetch('/settings/api-key'));
  },

  async setApiKey(apiKey: string): Promise<ApiKeyStatus> {
    return unwrap(
      await fetch('/settings/api-key', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      }),
    );
  },

  async clearApiKey(): Promise<ApiKeyStatus> {
    return unwrap(await fetch('/settings/api-key', { method: 'DELETE' }));
  },

  async startExtract(projectId: string, opts: ExtractStartOptions = {}): Promise<ExtractState> {
    return unwrap(
      await fetch(`/projects/${projectId}/extract${extractQuery(opts)}`, { method: 'POST' }),
    );
  },

  async getExtractState(projectId: string): Promise<ExtractState> {
    return unwrap(await fetch(`/projects/${projectId}/extract`));
  },

  async retryExtractTask(
    projectId: string,
    taskId: string,
    opts: ExtractStartOptions = {},
  ): Promise<ExtractState> {
    return unwrap(
      await fetch(
        `/projects/${projectId}/extract/retry/${encodeURIComponent(taskId)}${extractQuery(opts)}`,
        { method: 'POST' },
      ),
    );
  },

  async getDeviceModel(projectId: string): Promise<DeviceModel> {
    return unwrap(await fetch(`/projects/${projectId}/device-model`));
  },

  async saveDeviceModel(projectId: string, model: DeviceModel): Promise<DeviceModelSaveResponse> {
    return unwrap(
      await fetch(`/projects/${projectId}/device-model`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(model),
      }),
    );
  },

  async runExport(projectId: string): Promise<ExportResult> {
    return unwrap(
      await fetch(`/projects/${projectId}/export`, { method: 'POST' }),
    );
  },

  async getExportMetadata(projectId: string): Promise<ExportResult> {
    return unwrap(await fetch(`/projects/${projectId}/export`));
  },

  downloadIoListUrl(projectId: string): string {
    return `/projects/${projectId}/export/io-list`;
  },

  downloadCeUrl(projectId: string): string {
    return `/projects/${projectId}/export/ce`;
  },

  downloadSequenceDocUrl(projectId: string): string {
    return `/projects/${projectId}/export/sequence-doc`;
  },
};
