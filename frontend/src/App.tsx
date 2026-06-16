import { useCallback, useState } from 'react';
import { Header } from '@/components/Header';
import { TabBar, type TabDef } from '@/components/TabBar';
import { WizardTab, type WizardTabExposed } from '@/screens/WizardTab';
import { IgnitionTagBuilderTab } from '@/screens/IgnitionTagBuilderTab';
import { CommissioningWorkbookTab } from '@/screens/CommissioningWorkbookTab';
import { cn } from '@/lib/cn';

type TabId = 'wizard' | 'ignition-tags' | 'commissioning-workbook';

const TABS: ReadonlyArray<TabDef<TabId>> = [
  { id: 'wizard', label: 'Project Wizard' },
  { id: 'ignition-tags', label: 'Ignition Tag Builder' },
  { id: 'commissioning-workbook', label: 'Commissioning Workbook' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('wizard');
  const [headerInfo, setHeaderInfo] = useState<WizardTabExposed>({
    projectName: '',
    sourceFilename: '',
  });

  // Stable callback — WizardTab reports its header info via useEffect.
  const onHeaderInfoChange = useCallback((info: WizardTabExposed) => {
    setHeaderInfo(info);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <Header
        projectName={headerInfo.projectName}
        sourceFilename={headerInfo.sourceFilename}
        erpNumber={headerInfo.erpNumber}
      />
      <TabBar tabs={TABS} activeId={activeTab} onSelect={setActiveTab} />

      {/*
        Both tabs stay mounted simultaneously and visibility is toggled with
        CSS, so React state inside each tab persists across switches. We use
        Tailwind's `hidden` utility (display:none) rather than the HTML
        `hidden` attribute, because the inactive panel still carries
        `flex-1 flex-col` etc. and the `[hidden]` user-agent rule loses to
        Tailwind's explicit `display: flex`. The Tailwind hidden class wins
        because it's loaded later than the user-agent stylesheet.
      */}
      <div
        role="tabpanel"
        id="tabpanel-wizard"
        aria-labelledby="tab-wizard"
        aria-hidden={activeTab !== 'wizard'}
        className={cn(
          'flex-1 flex-col overflow-hidden',
          activeTab === 'wizard' ? 'flex' : 'hidden',
        )}
      >
        <WizardTab onHeaderInfoChange={onHeaderInfoChange} />
      </div>
      <div
        role="tabpanel"
        id="tabpanel-ignition-tags"
        aria-labelledby="tab-ignition-tags"
        aria-hidden={activeTab !== 'ignition-tags'}
        className={cn(
          'flex-1 flex-col overflow-hidden',
          activeTab === 'ignition-tags' ? 'flex' : 'hidden',
        )}
      >
        <IgnitionTagBuilderTab />
      </div>
      <div
        role="tabpanel"
        id="tabpanel-commissioning-workbook"
        aria-labelledby="tab-commissioning-workbook"
        aria-hidden={activeTab !== 'commissioning-workbook'}
        className={cn(
          'flex-1 flex-col overflow-hidden',
          activeTab === 'commissioning-workbook' ? 'flex' : 'hidden',
        )}
      >
        <CommissioningWorkbookTab />
      </div>
    </div>
  );
}
