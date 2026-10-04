import React from 'react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import GoogleTrajectoryMap from './GoogleTrajectoryMap.jsx';
import {loadGoogleMaps} from './lib/google-maps.js';
import {request} from './lib/api.js';
vi.mock('./lib/google-maps.js');vi.mock('./lib/api.js');vi.mock('mapbox-gl',()=>({default:{Map:()=>{throw new Error('legacy map used');}}}));
let markers,lines,maps;
const day={date:'2026-10-01',bounds:[139.7,35.6,139.8,35.7],events:[{id:'legacy',coordinates:[139.7,35.6],place:{name:'既存店舗'}},{id:'google',coordinates:[139.8,35.7],place:{name:'Google参照店舗',provider:'google'}},{id:'null',coordinates:null,place:{name:'未取得'}}],segments:[{stageNumber:1,coordinates:[[139.7,35.6],[139.8,35.7]]}]};
beforeEach(()=>{vi.resetAllMocks();markers=[];lines=[];maps=[];request.mockResolvedValue({googleMapsBrowserKey:'public-key',googleMapId:'DEMO_MAP_ID'});loadGoogleMaps.mockResolvedValue({Map:class{constructor(){this.fitBounds=vi.fn();maps.push(this);}setCenter(){}setZoom(){}},Polyline:class{constructor(opts){this.opts=opts;this.setMap=vi.fn();lines.push(this);}},AdvancedMarkerElement:class{constructor(opts){Object.assign(this,opts);markers.push(this);document.body.append(this.content);}}});});
afterEach(()=>{cleanup();markers.forEach(m=>m.content.remove());});
it('shows_legacy_and_google_visits_on_google_map_and_cleans_markers',async()=>{
 const view=render(<GoogleTrajectoryMap day={day} selectedEventId="google" onSelectEvent={vi.fn()}/>);await vi.waitFor(()=>expect(markers.length).toBe(2));expect(markers.map(m=>m.position)).toContainEqual({lng:139.7,lat:35.6});expect(lines.length).toBe(1);expect(maps[0].fitBounds).toHaveBeenCalled();expect(markers[1].content.getAttribute('aria-pressed')).toBe('true');view.unmount();expect(markers.every(m=>m.map===null)).toBe(true);markers.forEach(m=>m.content.remove());expect(lines[0].setMap).toHaveBeenCalledWith(null);
});
it('keyboard_selects_visit',async()=>{
 const select=vi.fn();render(<GoogleTrajectoryMap day={day} onSelectEvent={select}/>);await vi.waitFor(()=>expect(markers.length).toBe(2));const button=markers[0].content;button.focus();expect(document.activeElement).toBe(button);fireEvent.click(button);expect(select).toHaveBeenCalledWith('legacy');
});
it('missing_key_or_load_failure_keeps_timeline',async()=>{
 request.mockResolvedValueOnce({googleMapsBrowserKey:null});render(<GoogleTrajectoryMap day={day}/>);expect(await screen.findByText(/ブラウザ用キー/)).toBeTruthy();expect(screen.getByRole('button',{name:/再試行/}).disabled).toBe(false);fireEvent.click(screen.getByRole('button',{name:/再試行/}));loadGoogleMaps.mockRejectedValueOnce(new Error('fail'));expect(await screen.findByText(/地図を読み込めません/)).toBeTruthy();
});
it('stale_date_load_cannot_replace_current_map',async()=>{
 let done;loadGoogleMaps.mockReturnValueOnce(new Promise(r=>{done=r;}));const view=render(<GoogleTrajectoryMap day={day}/>);await vi.waitFor(()=>expect(loadGoogleMaps).toHaveBeenCalledTimes(1));view.rerender(<GoogleTrajectoryMap day={{...day,date:'2026-10-02'}}/>);await vi.waitFor(()=>expect(maps.length).toBe(1));done(await loadGoogleMaps.mock.results[1].value);await Promise.resolve();expect(maps.length).toBe(1);
});
