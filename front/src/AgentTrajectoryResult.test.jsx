import React from 'react';
import {it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import AgentTrajectoryResult from './AgentTrajectoryResult.jsx';
afterEach(cleanup);
it('shows_saved_and_excluded_without_approval_controls',()=>{
 const result={date:'2026-10-01',status:'partial',counts:{saved:2,existing:0,excluded:1},saved:[],existing:[],excluded:[{transactionId:'c',label:'店C',message:'複数の店舗候補が一致しました。'}]};
 const open=vi.fn();render(<AgentTrajectoryResult result={result} onOpenTrajectory={open}/>);
 expect(screen.getByText(/2件保存/)).toBeTruthy();expect(screen.getByText(/1件除外/)).toBeTruthy();expect(screen.getByText(/複数の店舗候補/)).toBeTruthy();expect(screen.queryByRole('button',{name:'確認して保存'})).toBeNull();
 fireEvent.click(screen.getByRole('link',{name:'2026-10-01の軌跡を開く'}));expect(open).toHaveBeenCalledWith('2026-10-01');
});
