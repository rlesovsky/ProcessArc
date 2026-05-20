import { useState } from 'react';
import { Header } from '@/components/Header';
import { StepBar } from '@/components/StepBar';
import { FooterNav } from '@/components/FooterNav';
import { ConfigureScreen, configureIsReady, type ConfigureState } from '@/screens/ConfigureScreen';
import { DiscoverScreen } from '@/screens/DiscoverScreen';
import { ExtractScreen } from '@/screens/ExtractScreen';
import { ReviewScreen } from '@/screens/ReviewScreen';
import { ExportScreen } from '@/screens/ExportScreen';
import { api, ApiError } from '@/api/client';
import type { PipelineStage, PlantConfiguration } from '@/api/types';
import { FAIRLESS_HILLS_DEMO } from '@/lib/demoPlant';

interface AppState {
  stage: PipelineStage;
  completed: PipelineStage[];
  busy: boolean;
  error: string | null;

  projectId: string | null;
  projectName: string;
  sourceFilename: string;

  configure: ConfigureState;
  plant: PlantConfiguration | null;

  // Demo-mode flags, surfaced by `?demo=...`. In dev these let us drive the
  // Extract screen without a real workbook or a real Claude API key.
  extractDryRun: boolean;
  extractSimulateFailureSheet: string | null;
}

const INITIAL: AppState = {
  stage: 'configure',
  completed: [],
  busy: false,
  error: null,
  projectId: null,
  projectName: '',
  sourceFilename: '',
  configure: { sequenceWorkbook: null, ioTemplate: null, ceProfile: null, projectName: '' },
  plant: null,
  extractDryRun: false,
  extractSimulateFailureSheet: null,
};

// Visual-only demo mode. Variants:
//   ?demo=discover  — Discover screen with the Fairless Hills stand-in
//   ?demo=extract   — Extract screen driving the dry-run extractor against a
//                     real backend project. Engineer must have a real project
//                     created already, or use ?demo=extract&project=<id>.
//                     Without a project id, this falls back to Discover.
//   &fail=<sheet>   — make the first attempt on that sheet fail (dry-run only)
function readDemoOverride(): Partial<AppState> | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const demo = params.get('demo');
  if (!demo) return null;

  if (demo === 'discover') {
    return {
      stage: 'discover',
      completed: ['configure'],
      projectId: 'demo',
      projectName: FAIRLESS_HILLS_DEMO.site_name,
      sourceFilename: FAIRLESS_HILLS_DEMO.workbook_filename,
      plant: FAIRLESS_HILLS_DEMO,
    };
  }

  if (demo === 'extract') {
    const projectId = params.get('project');
    if (!projectId) {
      // No real project — drop the engineer at Discover with a hint.
      return {
        stage: 'discover',
        completed: ['configure'],
        projectId: 'demo',
        projectName: FAIRLESS_HILLS_DEMO.site_name,
        sourceFilename: FAIRLESS_HILLS_DEMO.workbook_filename,
        plant: FAIRLESS_HILLS_DEMO,
      };
    }
    return {
      stage: 'extract',
      completed: ['configure', 'discover'],
      projectId,
      projectName: FAIRLESS_HILLS_DEMO.site_name,
      sourceFilename: '',
      plant: { ...FAIRLESS_HILLS_DEMO, confirmed: true },
      extractDryRun: true,
      extractSimulateFailureSheet: params.get('fail'),
    };
  }

  if (demo === 'review') {
    const projectId = params.get('project');
    if (!projectId) return null;
    return {
      stage: 'review',
      completed: ['configure', 'discover', 'extract'],
      projectId,
      projectName: FAIRLESS_HILLS_DEMO.site_name,
      sourceFilename: '',
      plant: { ...FAIRLESS_HILLS_DEMO, confirmed: true, erp_number: '554' },
    };
  }

  return null;
}

const ORDER: PipelineStage[] = ['configure', 'discover', 'extract', 'review', 'export'];

export default function App() {
  const [s, setS] = useState<AppState>(() => ({ ...INITIAL, ...(readDemoOverride() ?? {}) }));

  const markCompleted = (stage: PipelineStage, prev: PipelineStage[]) =>
    prev.includes(stage) ? prev : [...prev, stage];

  async function handleContinueConfigure() {
    if (!configureIsReady(s.configure)) return;
    setS(p => ({ ...p, busy: true, error: null }));
    try {
      const res = await api.createProject({
        sequenceWorkbook: s.configure.sequenceWorkbook!,
        ioTemplate: s.configure.ioTemplate!,
        ceProfile: s.configure.ceProfile,
        projectName: s.configure.projectName,
      });
      setS(p => ({
        ...p,
        busy: false,
        projectId: res.project_id,
        projectName: res.project_name,
        sourceFilename: res.plant_configuration.workbook_filename,
        plant: res.plant_configuration,
        stage: 'discover',
        completed: markCompleted('configure', p.completed),
      }));
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      setS(p => ({ ...p, busy: false, error: msg }));
    }
  }

  async function handleContinueDiscover() {
    if (!s.plant || !s.projectId) return;
    setS(p => ({ ...p, busy: true, error: null }));
    try {
      await api.confirmPlantConfiguration(s.projectId, s.plant);
      setS(p => ({
        ...p,
        busy: false,
        stage: 'extract',
        completed: markCompleted('discover', p.completed),
      }));
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      setS(p => ({ ...p, busy: false, error: msg }));
    }
  }

  function handleBack() {
    const idx = ORDER.indexOf(s.stage);
    if (idx <= 0) return;
    setS(p => ({ ...p, stage: ORDER[idx - 1] }));
  }

  const canBack = ORDER.indexOf(s.stage) > 0;
  let canContinue = false;
  let continueLabel = 'Continue';
  let onContinue: (() => void) | undefined;

  if (s.stage === 'configure') {
    canContinue = configureIsReady(s.configure);
    continueLabel = 'Discover plant';
    onContinue = handleContinueConfigure;
  } else if (s.stage === 'discover') {
    canContinue = s.plant !== null;
    continueLabel = 'Confirm & extract';
    onContinue = handleContinueDiscover;
  } else if (s.stage === 'extract') {
    canContinue = s.completed.includes('extract');
    continueLabel = 'Review devices';
    onContinue = () => setS(p => ({ ...p, stage: 'review' }));
  } else if (s.stage === 'review') {
    // The Review screen's own Save & Continue button drives the advance; the
    // footer Continue stays disabled and unused on this screen. Going back is
    // still allowed via the footer Back button.
    canContinue = false;
    continueLabel = 'Save & continue';
    onContinue = undefined;
  }

  return (
    <div className="flex h-full flex-col">
      <Header
        projectName={s.projectName}
        sourceFilename={s.sourceFilename}
        erpNumber={s.plant?.erp_number}
      />
      <StepBar
        activeStage={s.stage}
        completedStages={s.completed}
        onJumpTo={(t) => setS(p => ({ ...p, stage: t }))}
      />

      <main className="flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-5xl px-6 py-6">
          {s.error && (
            <div className="mb-4 rounded-card border border-danger-500/40 bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500">
              {s.error}
            </div>
          )}

          {s.stage === 'configure' && (
            <ConfigureScreen
              value={s.configure}
              onChange={(next) => setS(p => ({ ...p, configure: next }))}
            />
          )}

          {s.stage === 'discover' && s.plant && (
            <DiscoverScreen
              plant={s.plant}
              onTogglePlantIdle={(next) => setS(p => ({ ...p, plant: next }))}
            />
          )}

          {s.stage === 'extract' && s.projectId && (
            <ExtractScreen
              projectId={s.projectId}
              dryRun={s.extractDryRun}
              simulateFailureSheet={s.extractSimulateFailureSheet}
              onComplete={() =>
                setS(p => ({ ...p, completed: markCompleted('extract', p.completed) }))
              }
            />
          )}
          {s.stage === 'review' && s.projectId && s.plant && (
            <ReviewScreen
              projectId={s.projectId}
              plant={s.plant}
              onAdvance={() =>
                setS(p => ({
                  ...p,
                  stage: 'export',
                  completed: markCompleted('review', p.completed),
                }))
              }
            />
          )}
          {s.stage === 'export' && s.projectId && s.plant && (
            <ExportScreen projectId={s.projectId} plant={s.plant} />
          )}
        </div>
      </main>

      <FooterNav
        canBack={canBack}
        canContinue={canContinue}
        continueLabel={continueLabel}
        busy={s.busy}
        onBack={handleBack}
        onContinue={onContinue}
      />
    </div>
  );
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-card border border-dashed border-ink-300 bg-white p-12 text-center dark:border-ink-600 dark:bg-ink-800">
      <h1 className="mb-2 text-lg font-semibold text-ink-700 dark:text-ink-200">{title}</h1>
      <p className="text-sm text-ink-500 dark:text-ink-400">{body}</p>
    </section>
  );
}
