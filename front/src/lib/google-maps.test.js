import {it,expect,vi,afterEach} from 'vitest';
import {loadGoogleMaps} from './google-maps.js';
afterEach(()=>{document.querySelectorAll('script[data-kakei-google-maps]').forEach(s=>s.remove());delete window.google;});
it('loads_script_once_and_retries_failures',async()=>{
 const first=loadGoogleMaps({browserKey:'public-key',mapId:'DEMO_MAP_ID'}),second=loadGoogleMaps({browserKey:'public-key'});
 const scripts=document.querySelectorAll('script[data-kakei-google-maps]');expect(scripts.length).toBe(1);
 const url=new URL(scripts[0].src);expect(url.searchParams.get('loading')).toBe('async');expect(url.searchParams.get('v')).toBe('quarterly');expect(url.searchParams.get('language')).toBe('ja');
 const maps={Map:vi.fn(),Polyline:vi.fn(),marker:{AdvancedMarkerElement:vi.fn()}};window.google={maps};window[url.searchParams.get('callback')]();expect((await first).Map).toBe(maps.Map);expect((await second).AdvancedMarkerElement).toBe(maps.marker.AdvancedMarkerElement);
});
it('rejects_missing_browser_key',async()=>{await expect(loadGoogleMaps({browserKey:null})).rejects.toThrow(/設定/);});
