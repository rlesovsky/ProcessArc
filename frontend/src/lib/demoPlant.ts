import type { PlantConfiguration } from '@/api/types';

// Static stand-in matching the real Fairless Hills file, for visual review of
// the Discover screen without needing an actual upload+backend call.
// Reached via http://localhost:5173/?demo=discover

export const FAIRLESS_HILLS_DEMO: PlantConfiguration = {
  site_name: 'Fairless Hills',
  erp_number: '',
  workbook_filename: 'Fairless Hills Graphics and Sequence.xlsx',
  cylinders: [
    { number: 1, name: 'Cylinder 1', sequence_sheet: 'Cylinder 1 Sequencing', is_idle: false, status_note: '' },
    { number: 2, name: 'Cylinder 2', sequence_sheet: 'Cylinder 2 Sequencing', is_idle: false, status_note: '' },
  ],
  mix_systems: [
    { number: 1, name: 'ECO Mix', sequence_sheet: 'ECO Mix Sequencing', chemistry: 'ECO' },
    { number: 2, name: 'MCA Mix', sequence_sheet: 'MCA Mix Sequencing', chemistry: 'MCA' },
  ],
  tanks: [
    mkTank({ tank_id: '1',         chemical: 'MCA',       cylinder_used: 1 }),
    mkTank({ tank_id: 'MCA Conc',  chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: '3',         chemical: 'ECO',       cylinder_used: 2 }),
    mkTank({ tank_id: '4',         chemical: 'Idle Tank', cylinder_used: 1, is_idle: true }),
    mkTank({ tank_id: '5',         chemical: 'ECO',       cylinder_used: 1 }),
    mkTank({ tank_id: 'ECO WATER', chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: 'MCA Water', chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: 'ECO COLOR', chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: 'ECO Conc',  chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: 'HE14',      chemical: '',          cylinder_used: null }),
    mkTank({ tank_id: 'HE45',      chemical: '',          cylinder_used: null }),
  ],
  sequence_sheets: [
    'Cylinder 1 Sequencing',
    'Cylinder 2 Sequencing',
    'ECO Mix Sequencing',
    'MCA Mix Sequencing',
  ],
  all_sheets: [],
  warnings: [],
  confirmed: false,
};

function mkTank(p: { tank_id: string; chemical: string; cylinder_used: number | null; is_idle?: boolean }) {
  return {
    tank_id: p.tank_id,
    chemical: p.chemical,
    cylinder_used: p.cylinder_used,
    is_idle: p.is_idle ?? false,
    diameter_in: null, length_in: null, target_volume: null,
    min_volume: null, max_volume: null, density: null,
    source_row: null, raw: {},
  };
}
