import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import GooglePlaceResults from '../components/places/GooglePlaceResults.jsx';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('google_results_are_ephemeral_and_attributed',async()=>{
 const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({name:'Google店舗',address:'Google住所',googleMapsUri:'https://maps.google.com/?cid=1',attributions:[{provider:'資料提供',providerUri:'https://example.com'}]})});vi.stubGlobal('fetch',fetch);
 const view=render(<GooglePlaceResults placeIds={['one']}/>);expect(await screen.findByText('Google店舗')).toBeTruthy();expect(screen.getByText('Google Maps')).toBeTruthy();expect(screen.getByRole('link',{name:'Google Mapsで見る'}).getAttribute('href')).toContain('cid=1');expect(screen.getByText('資料提供')).toBeTruthy();expect(fetch.mock.calls[0][0]).toBe('/api/places/google/one');
 view.rerender(<GooglePlaceResults placeIds={[]}/>);expect(screen.queryByText('Google店舗')).toBeNull();
});
it('discards slow response when references change',async()=>{
 let resolve;vi.stubGlobal('fetch',vi.fn().mockReturnValue(new Promise(r=>{resolve=r;})));
 const view=render(<GooglePlaceResults placeIds={['one']}/>);view.rerender(<GooglePlaceResults placeIds={[]}/>);resolve({ok:true,json:async()=>({name:'古い候補'})});await Promise.resolve();expect(screen.queryByText('古い候補')).toBeNull();
});
it('selects by reference and exposes disabled selected state',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({name:'店舗',address:'住所'})}));
 const select=vi.fn();const view=render(<GooglePlaceResults placeIds={['one']} onSelect={select}/>);
 const button=await screen.findByRole('button',{name:'この店舗を選択'});button.click();expect(select).toHaveBeenCalledWith('one');
 view.rerender(<GooglePlaceResults placeIds={['one']} selectedPlaceId="one" disabled onSelect={select}/>);
 expect(screen.getByRole('button',{name:'選択済み'}).disabled).toBe(true);expect(screen.getByRole('button',{name:'選択済み'}).getAttribute('aria-pressed')).toBe('true');
});
