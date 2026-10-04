import React from 'react';
import {it,expect,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import CoordinateEvidence from './CoordinateEvidence.jsx';
afterEach(cleanup);
it('address_matched_evidence_keeps_kind_after_confirmation',()=>{
 const evidence={version:2,status:'address_matched',method:'geolonia_address',precision:'address',verification:'user_confirmed',note:'店舗の入口は未確認。',addressMatch:{matchedAddress:'東京都文京区本郷一丁目2-3'}};
 render(<CoordinateEvidence evidence={evidence}/>);
 expect(screen.getByText('住所に対応する座標')).toBeTruthy();expect(screen.getByText(/番地・住居番号まで照合/)).toBeTruthy();
 expect(screen.getByText(/本郷一丁目2-3/)).toBeTruthy();expect(screen.getByText('利用者が位置を確認済み')).toBeTruthy();
 expect(screen.queryByText('掲載座標')).toBeNull();
 expect(screen.getByRole('link',{name:/CC BY 4.0/}).getAttribute('href')).toBe('https://creativecommons.org/licenses/by/4.0/');
});
it('keeps estimate status, basis and uncertainty after confirmation',()=>{
 render(<CoordinateEvidence evidence={{status:'estimated',method:'relative_offset',precision:'nearby',verification:'user_confirmed',note:'誤差範囲は未確認。',basis:{anchorName:'施設',anchorAddress:'福岡市',distanceMeters:100,bearingDegrees:90}}}/>);
 expect(screen.getByText('推定位置')).toBeTruthy();expect(screen.getByText(/施設/)).toBeTruthy();expect(screen.getByText(/東へ100m/)).toBeTruthy();expect(screen.getByText(/誤差範囲/)).toBeTruthy();expect(screen.getByText('利用者が位置を確認済み')).toBeTruthy();
});
it('published evidence uses human labels and never HTML',()=>{
 const {container}=render(<CoordinateEvidence evidence={{status:'published',method:'structured_geo',precision:'point',note:'<img src=x>',verification:'needs_confirmation'}}/>);
 expect(screen.getByText('掲載座標')).toBeTruthy();expect(screen.getByText(/構造化データ/)).toBeTruthy();expect(container.querySelector('img')).toBeNull();
});
