// @vitest-environment node
import {it,expect} from 'vitest';
import {mockMerchantPlace,mockPlaceDetails,retainMockMerchantPlace} from '../../dev/mock-merchant-place-fixtures.mjs';
it('retrieves fictional Details and clears changed identity references',()=>{const old={type:'expense',merchant:'架空ストア',merchantAddress:null,merchantPlace:mockMerchantPlace};expect(mockPlaceDetails(mockMerchantPlace.placeId).address).toBe('架空県サンプル市1-2-3');expect(retainMockMerchantPlace(old,{...old,amount:250})).toEqual(mockMerchantPlace);for(const edit of [{merchant:'別店舗'},{merchantAddress:'本人住所'},{type:'income'}])expect(retainMockMerchantPlace(old,{...old,...edit})).toBeUndefined();});
it('mock API preserves references on unchanged full PUT but clears every explicit address PATCH',async()=>{
 const {mockApi}=await import('../../dev/mock-api.mjs');let middleware;
 mockApi().configureServer({config:{env:{}},middlewares:{use:value=>{middleware=value;}}});
 async function request(url,method='GET',body){let result;await middleware({url,method,async *[Symbol.asyncIterator](){if(body)yield JSON.stringify(body);}},{setHeader(){},end(value){result={status:this.statusCode,value:value?JSON.parse(value):null};}},()=>{});return result;}
 const old=(await request('/api/transactions')).value.transactions.find(t=>t.merchantPlace);
 expect((await request('/api/places/google/'+old.merchantPlace.placeId)).value.address).toBe('架空県サンプル市1-2-3');
 const {id,timeEstimated,merchantPlace,...draft}=old;
 expect((await request('/api/transactions/'+id,'PUT',{...draft,amount:250,items:[]})).value.transaction.merchantPlace).toEqual(merchantPlace);
 expect((await request('/api/transaction-addresses/'+id,'PATCH',{merchantAddress:null,expected:{merchant:old.merchant,merchantAddress:null}})).value.transaction.merchantPlace).toBeUndefined();
 expect((await request('/api/transaction-addresses/'+id,'PATCH',{merchantAddress:'本人住所',expected:{merchant:old.merchant,merchantAddress:null}})).value.transaction.merchantPlace).toBeUndefined();
 expect((await request('/api/transactions/'+id,'PUT',{...draft,merchant:'店舗を変更'})).value.transaction.merchantPlace).toBeUndefined();
});
