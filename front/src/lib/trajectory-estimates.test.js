import {it,expect,vi} from 'vitest';
import {attachEstimatedMarkers} from './trajectory-estimates.js';
it('creates decorative rings only for valid estimates and removes them',()=>{
 const markers=[];class Marker{constructor(options){this.options=options;this.remove=vi.fn();markers.push(this);}setLngLat(coords){this.coords=coords;return this;}addTo(map){this.map=map;return this;}}
 const event={coordinates:[130,33],place:{coordinateEvidence:{status:'estimated'}}};
 const release=attachEstimatedMarkers({},[event,{...event,locationStatus:'needs_review'},{...event,coordinates:[Infinity,33]},{...event,place:{}}],Marker);
 expect(markers.length).toBe(1);expect(markers[0].options.element.getAttribute('aria-hidden')).toBe('true');expect(markers[0].options.element.style.pointerEvents).toBe('none');release();expect(markers[0].remove).toHaveBeenCalledOnce();
});
