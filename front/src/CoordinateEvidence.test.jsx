import React from 'react';
import {it,expect,afterEach} from 'vitest';
import {render,screen,cleanup} from '@testing-library/react';
import CoordinateEvidence from './CoordinateEvidence.jsx';
afterEach(cleanup);
it('keeps estimate status, basis and uncertainty after confirmation',()=>{
 render(<CoordinateEvidence evidence={{status:'estimated',method:'relative_offset',precision:'nearby',verification:'user_confirmed',note:'誤差範囲は未確認。',basis:{anchorName:'施設',anchorAddress:'福岡市',distanceMeters:100,bearingDegrees:90}}}/>);
 expect(screen.getByText('推定位置')).toBeTruthy();expect(screen.getByText(/施設/)).toBeTruthy();expect(screen.getByText(/東へ100m/)).toBeTruthy();expect(screen.getByText(/誤差範囲/)).toBeTruthy();expect(screen.getByText('利用者が位置を確認済み')).toBeTruthy();
});
it('published evidence uses human labels and never HTML',()=>{
 const {container}=render(<CoordinateEvidence evidence={{status:'published',method:'structured_geo',precision:'point',note:'<img src=x>',verification:'needs_confirmation'}}/>);
 expect(screen.getByText('掲載座標')).toBeTruthy();expect(screen.getByText(/構造化データ/)).toBeTruthy();expect(container.querySelector('img')).toBeNull();
});
