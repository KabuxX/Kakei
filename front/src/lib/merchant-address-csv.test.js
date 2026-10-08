import {expect,it} from 'vitest';
import {serializeTransactionsCsv} from './transaction-data.js';
it('appends direct and deduplicated related addresses and escapes formula cells',()=>{
 const record={id:'a',type:'expense',title:'買物',date:'2026-10-01T12:00',category:'食費',amount:100,merchantAddress:'=1+1'};
 const csv=serializeTransactionsCsv([record],[{transactionId:'a',places:[{address:'住所,"A"\nB'},{address:'住所,"A"\nB'}]}]);
 expect(csv).toContain('"取引先住所","関連軌跡住所"');expect(csv).toContain('"\'=1+1","住所,""A""\nB"');
 for(const prefix of ['=','+','-','@','\t','\r'])expect(serializeTransactionsCsv([record],[{transactionId:'a',places:[{address:prefix+'formula'}]}])).toContain(`"'${prefix}formula"`);
});

it('does not export Google display data from a saved reference',()=>{
 const record={id:'a',type:'expense',title:'買物',date:'2026-10-01T12:00',category:'食費',amount:100,merchantAddress:null,merchantPlace:{provider:'google',placeId:'fixture-one',method:'google_selected',address:'一時Google住所',name:'一時Google店舗'}};
 const csv=serializeTransactionsCsv([record]);
 expect(csv).not.toContain('一時Google');expect(csv).not.toContain('fixture-one');
});
