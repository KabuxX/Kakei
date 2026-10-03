import { normalizeMerchantAddress,parseExpenseDraft } from '../src/lib/transaction-data.js';
import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { assignEstimatedTransactionDatetimes, isValidTransactionDateTime } from '../src/lib/transaction-datetime.js';

const fixtureUrl = new URL('../src/data/september-transactions.json', import.meta.url);

function send(response, status, payload) {
  response.statusCode = status;
  if (payload === undefined) return response.end();
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(payload));
}

export function mockApi() {
  return {
    name: 'kakei-json-api',
    configureServer(server) {
      let transactions = assignEstimatedTransactionDatetimes(JSON.parse(readFileSync(fixtureUrl, 'utf8')));
      const timeline = JSON.parse(readFileSync(new URL('../src/data/september-timeline.json', import.meta.url), 'utf8'));
      const statusFor = (record, place) => !record?.merchantAddress ? 'trajectory_only' : record.merchantAddress.normalize('NFKC').replace(/\s/g,'') === place?.address?.normalize('NFKC').replace(/\s/g,'') ? 'matched' : 'needs_review';
      const contextFor = record => ({transactionId:record.id,places:record.type==='expense'?[...new Set(timeline.days.flatMap(d=>d.events).filter(e=>e.transactionId===record.id).map(e=>e.placeId))].map(id=>({...timeline.places[id],placeId:id,status:statusFor(record,timeline.places[id])})):[]});
      server.middlewares.use(async (request, response, next) => {
        const path = new URL(request.url, 'http://localhost').pathname;
        if (!path.startsWith('/api/')) return next();

        if (path === '/api/transaction-addresses' && request.method === 'GET') {
          return send(response,200,{addresses:transactions.map(contextFor).filter(c=>c.places.length)});
        }
        if (path.startsWith('/api/transaction-addresses/')) {
          const id=decodeURIComponent(path.slice('/api/transaction-addresses/'.length));
          const record=transactions.find(t=>t.id===id);
          if(!record)return send(response,404,{error:{message:'取引が見つかりません。'}});
          if(request.method==='GET')return send(response,200,{address:contextFor(record)});
          if(request.method==='PATCH') {
            try {
              let raw='';for await(const chunk of request)raw+=chunk;
              const body=JSON.parse(raw);
              if(record.type!=='expense'||!body||Object.keys(body).sort().join()!=='expected,merchantAddress'||!body.expected||Object.keys(body.expected).sort().join()!=='merchant,merchantAddress')throw new Error('住所と変更前の値を指定してください。');
              const address=normalizeMerchantAddress(body.merchantAddress);
              if(body.expected.merchant!==(record.merchant??null)||body.expected.merchantAddress!==(record.merchantAddress??null))return send(response,409,{error:{message:'取引が変更されました。再読み込みしてください。'}});
              record.merchantAddress=address;return send(response,200,{transaction:record});
            }catch(error){return send(response,400,{error:{message:error.message,field:'merchantAddress'}});}
          }
        }
        if (path === '/api/status' && request.method === 'GET') {
          return send(response, 200, { initialized: true });
        }
        if (path === '/api/map-config' && request.method === 'GET') {
          const token=server.config.env.VITE_MAPBOX_ACCESS_TOKEN?.trim();
          return send(response, 200, { mapboxPublicToken: token?.startsWith('pk.') ? token : null });
        }
        if (path === '/api/trajectory' && request.method === 'GET') {
          return send(response, 200, { dates: timeline.days.map((day) => day.date) });
        }
        if (path.startsWith('/api/trajectory/') && request.method === 'GET') {
          const days = timeline.days.filter((day) => day.date === path.split('/').at(-1)).map(day=>({...day,events:day.events.map(e=>({...e,locationStatus:statusFor(transactions.find(t=>t.id===e.transactionId),timeline.places[e.placeId])}))}));
          return days.length ? send(response, 200, { places: timeline.places, days }) : send(response, 404, { error: { code: 'not_found' } });
        }
        if (path === '/api/transactions' && request.method === 'GET') {
          return send(response, 200, { transactions });
        }
        if (path === '/api/transactions' && request.method === 'POST') {
          try {
            let body = '';
            for await (const chunk of request) body += chunk;
            const draft = JSON.parse(body);
            if (!draft || typeof draft !== 'object' || Array.isArray(draft)) throw new Error('invalid draft');
            if (!isValidTransactionDateTime(draft.date)) {
              return send(response, 400, { error: { code: 'validation_error', message: '正しい日時を入力してください。', field: 'date' } });
            }
            const transaction = { ...draft, timeEstimated: false, id: `dev-${randomUUID()}` };
            if(transaction.type==='expense')transaction.merchantAddress=normalizeMerchantAddress(draft.merchantAddress);
            else delete transaction.merchantAddress;
            transactions = [...transactions, transaction];
            return send(response, 201, { transaction });
          } catch {
            return send(response, 400, { error: { code: 'validation_error', message: '取引データを確認してください。' } });
          }
        }
        if (path.startsWith('/api/transactions/') && request.method === 'PUT') {
          try {
            const id=decodeURIComponent(path.slice('/api/transactions/'.length));
            const index=transactions.findIndex(record=>record.id===id);
            if(index<0)return send(response,404,{error:{message:'取引が見つかりません。'}});
            let raw='';for await(const chunk of request)raw+=chunk;
            const draft=JSON.parse(raw),old=transactions[index];
            if(!draft||Array.isArray(draft)||!isValidTransactionDateTime(draft.date)||!['expense','income'].includes(draft.type)||typeof draft.title!=='string'||!draft.title.trim())throw new Error('取引データを確認してください。');
            const details=draft.type==='expense'?parseExpenseDraft({merchant:draft.merchant,merchantAddress:Object.hasOwn(draft,'merchantAddress')?draft.merchantAddress:old.merchantAddress,paymentMethod:draft.paymentMethod,itemRows:draft.items||[],manualAmount:draft.amount}):{};
            if(!Number.isInteger(draft.amount)||draft.amount<1||draft.amount>999999999)throw new Error('金額を確認してください。');
            const transaction={id,title:draft.title.trim(),type:draft.type,date:draft.date,category:draft.category,amount:draft.amount,...details,timeEstimated:old.date===draft.date&&!draft.confirmTime?old.timeEstimated:false};
            transactions[index]=transaction;return send(response,200,{transaction});
          }catch(error){return send(response,400,{error:{code:'validation_error',message:error.message,field:error.field}});}
        }
        if (path === '/api/samples' && request.method === 'DELETE') {
          const remaining = transactions.filter((item) => !item.id.startsWith('sample-'));
          const deletedCount = transactions.length - remaining.length;
          transactions = remaining;
          return send(response, 200, { deletedCount });
        }
        if (path.startsWith('/api/transactions/') && request.method === 'DELETE') {
          let id;
          try { id = decodeURIComponent(path.slice('/api/transactions/'.length)); }
          catch { return send(response, 400, { error: { code: 'invalid_id' } }); }
          if (!transactions.some((item) => item.id === id)) return send(response, 404, { error: { code: 'not_found' } });
          transactions = transactions.filter((item) => item.id !== id);
          return send(response, 204);
        }
        return send(response, 404, { error: { code: 'not_found' } });
      });
    },
  };
}
