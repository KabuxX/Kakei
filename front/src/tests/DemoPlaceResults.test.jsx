import React,{act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect} from 'vitest';import DemoPlaceResults from '../components/places/DemoPlaceResults.jsx';
it('displays independent sources and unconfirmed positions without fetching',async()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;const host=document.createElement('div');const root=createRoot(host);await act(async()=>root.render(<DemoPlaceResults placeIds={['p']} places={{p:{name:'店舗',address:'東京都',sourceUrl:'https://example.org',coordinates:null,demoPositionUnconfirmed:true}}}/>));expect(host.textContent).toContain('店舗');expect(host.textContent).toContain('位置は未確認');expect(host.querySelector('a').href).toBe('https://example.org/');await act(async()=>root.unmount());
});
