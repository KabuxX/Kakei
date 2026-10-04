import { layers, namedFlavor } from '@protomaps/basemaps';
import manifest from './manifest.json';
/** MapLibre v6 style using bundled Japanese web font and no sprite/glyph server. */
export function createOfflineStyle(baseUrl) {
  const base = new URL(baseUrl, globalThis.location?.href);
  const flavor = { ...namedFlavor('light'), regular:'Noto Sans JP',bold:'Noto Sans JP',italic:'Noto Sans JP' };
  const mapLayers = layers('basemap',flavor,{lang:'ja'})
    .filter(l=>!['buildings','pois'].includes(l['source-layer']) && !l.layout?.['icon-image'])
    .map(l=>l.type==='symbol'?{...l,layout:{...l.layout,'text-font':['Noto Sans JP']}}:l);
  return { version:8, name:'Tokyo offline demo',
    'font-faces':{'Noto Sans JP':new URL('maps/fonts/NotoSansJP.ttf',base).href},
    sources:{basemap:{type:'vector',url:`pmtiles://${new URL('maps/tokyo.pmtiles',base).href}`,attribution:'© OpenStreetMap contributors · Protomaps · Natural Earth',bounds:manifest.bounds,minzoom:0,maxzoom:manifest.tileMaxZoom}},
    layers:mapLayers,
  };
}
