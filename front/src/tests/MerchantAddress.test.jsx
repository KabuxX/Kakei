import {expect,it} from 'vitest';
import {parseExpenseDraft} from '../lib/transaction-data.js';
it('keeps optional addresses and enforces the Unicode limit',()=>{
 const draft={merchant:'店',paymentMethod:'cash',itemRows:[],manualAmount:100,merchantAddress:'𠮷'.repeat(500)};
 expect(parseExpenseDraft(draft).merchantAddress).toBe('𠮷'.repeat(500));
 expect(()=>parseExpenseDraft({...draft,merchantAddress:'𠮷'.repeat(501)})).toThrow();
});
