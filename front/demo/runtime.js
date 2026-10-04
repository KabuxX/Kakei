import snapshot from './data/snapshot.json';
import manifest from './data/manifest.json';
import {createDemoFetch} from './api.js';
import {validateDemoSnapshot} from './validate.js';
validateDemoSnapshot(snapshot,manifest);
export const isDemo=true;
export const readOnly=true;
export const snapshotTime=Date.parse(snapshot.exportedAt)/1000;
export const getInitialMonth=()=>{const [year,month]=manifest.latestMonth.split('-').map(Number);return new Date(year,month-1,1);};
export const apiFetch=createDemoFetch(snapshot);
export const assetUrl=path=>`${import.meta.env.BASE_URL}${path.replace(/^\//,'')}`;
export const receiptUrl=id=>snapshot.receipts[id]?assetUrl(snapshot.receipts[id].path):'';
// Filled with the local renderer in Task 5; never loads the Google renderer.
const maps=import.meta.glob('../src/components/trajectory/OfflineTrajectoryMap.jsx');
export const loadTrajectoryMap=()=>maps['../src/components/trajectory/OfflineTrajectoryMap.jsx']?.() || Promise.reject(new Error('Local map is not ready'));
export const demoPlaces=snapshot.placeLookup;
