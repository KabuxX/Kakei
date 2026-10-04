import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import PlaceSources,{renderCitedText} from '../components/places/PlaceSources.jsx';
afterEach(cleanup);
it('dataset_source_and_license_are_distinct_from_store_sources',()=>{
 render(<PlaceSources sources={[{id:'g',title:'データ出典',url:'https://example.com/data'},{id:'s',title:'店舗案内',url:'https://example.com/shop'}]} coordinateEvidence={{status:'address_matched',method:'geolonia_address',addressMatch:{matchedAddress:'東京都文京区本郷一丁目2-3',fetches:[{sourceId:'g'}]}}}/>);
 expect(screen.getByRole('link',{name:/座標データ.*データ出典/})).toBeTruthy();
 expect(screen.getByRole('link',{name:/店舗情報.*店舗案内/})).toBeTruthy();
 expect(screen.getByRole('link',{name:/CC BY 4.0/})).toBeTruthy();
});
const source={id:'s1',title:'日本語の長い店舗情報'.repeat(15),url:'https://example.com/store?id=12'};
it('unknown_citation_stays_plain_text and unsafe links cannot become anchors',()=>{
 const {container}=render(<><p>{renderCitedText('<img src=x> [source:s1] [source:unknown] [source:bad]',[source,{id:'bad',url:'javascript:alert(1)',title:'bad'}])}</p><PlaceSources sources={[source,{id:'bad',url:'javascript:alert(1)'}]}/></>);
 expect(screen.getAllByRole('link')).toHaveLength(2);
 expect(screen.getByText(/source:unknown/)).toBeTruthy();expect(container.querySelector('img')).toBeNull();
 expect(screen.getByRole('link',{name:/^店舗情報/}).getAttribute('href')).toBe(source.url);
 expect(screen.getAllByRole('link')[0].getAttribute('rel')).toContain('noopener');
});
it('keeps legacy sources and separates interpolated coordinate evidence',()=>{
 render(<PlaceSources sourceUrl="https://example.com/old" attribution="© Mapbox" geocoding={{provider:'mapbox',accuracy:'interpolated'}}/>);
 expect(screen.getByRole('link',{name:/地点の出典を見る/})).toBeTruthy();expect(screen.getByText(/座標.*Mapbox.*補間/)).toBeTruthy();
});
