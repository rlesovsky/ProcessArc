// Mirrors backend/model/plant.py + backend/model/project.py.
// Kept hand-written for now; can be code-generated from OpenAPI later.

export type PipelineStage =
  | 'configure'
  | 'discover'
  | 'extract'
  | 'review'
  | 'export';

export interface CylinderSystem {
  number: number;
  name: string;
  sequence_sheet: string | null;
  is_idle: boolean;
  status_note: string;
}

export interface MixSystem {
  number: number;
  name: string;
  sequence_sheet: string | null;
  chemistry: string;
}

export interface TankRecord {
  tank_id: string;
  chemical: string;
  cylinder_used: number | null;
  is_idle: boolean;
  diameter_in: number | null;
  length_in: number | null;
  target_volume: number | null;
  min_volume: number | null;
  max_volume: number | null;
  density: number | null;
  source_row: number | null;
  raw: Record<string, string | number | null>;
}

export interface PlantConfiguration {
  site_name: string;
  erp_number: string;
  workbook_filename: string;
  cylinders: CylinderSystem[];
  mix_systems: MixSystem[];
  tanks: TankRecord[];
  sequence_sheets: string[];
  all_sheets: string[];
  warnings: string[];
  confirmed: boolean;
}

export type ExtractTaskKind = 'tables' | 'prose_sheet';
export type ExtractTaskStatus = 'queued' | 'running' | 'done' | 'failed';

export interface ExtractTask {
  id: string;
  kind: ExtractTaskKind;
  label: string;
  status: ExtractTaskStatus;
  detail: string;
  started_at: string | null;
  finished_at: string | null;
  sheet_name: string | null;
}

export interface ExtractState {
  started_at: string | null;
  finished_at: string | null;
  tasks: ExtractTask[];
  device_count: number;
}

// Mirrors backend/model/device.py.
export type DeviceClassValue = 'Pump' | 'Valve' | 'VFD Pump' | 'Control Valve' | 'Tank';
export type SystemKindValue = 'Cylinders' | 'Mixing';
export type SourceTypeValue = 'Sequence Prose' | 'Table' | 'Manual' | 'P&ID';
export type ConfidenceValue = 'High' | 'Needs Review';
export type ReviewStatusValue = 'Pending' | 'Confirmed' | 'Excluded';

export interface DeviceRecord {
  canonical_id: string;
  device_class: DeviceClassValue;
  system: SystemKindValue;
  system_number: number | null;
  base_name: string;
  description: string;
  source_reference: string;
  source_type: SourceTypeValue;
  confidence: ConfidenceValue;
  ignition_udt_type: string;
  ignition_folder: string;
  ce_output_tag: string;
  register_values: Record<string, string | number>;
  notes: string;
  review_status: ReviewStatusValue;
}

export interface DeviceModel {
  devices: DeviceRecord[];
}

export interface DeviceModelSaveResponse {
  project_id: string;
  stage: PipelineStage;
  advanced: boolean;
  device_count: number;
  unresolved_flags: boolean;
}

export interface ExportFile {
  filename: string;
  size_bytes: number;
  rendered_at: string;
}

export interface ExportResult {
  io_list: ExportFile | null;
  ce: ExportFile | null;
  sequence_doc: ExportFile | null;
}

export interface CreateProjectResponse {
  project_id: string;
  project_name: string;
  stage: PipelineStage;
  plant_configuration: PlantConfiguration;
}

export interface ConfirmResponse {
  project_id: string;
  stage: PipelineStage;
  confirmed: true;
}

export interface HealthResponse {
  status: string;
  version: string;
  has_api_key: boolean;
  claude_model: string;
}

export interface ApiKeyStatus {
  configured: boolean;
  masked: string | null;
  model: string;
}
