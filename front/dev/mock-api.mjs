import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';

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
      let transactions = JSON.parse(readFileSync(fixtureUrl, 'utf8'));
      server.middlewares.use(async (request, response, next) => {
        const path = new URL(request.url, 'http://localhost').pathname;
        if (!path.startsWith('/api/')) return next();

        if (path === '/api/status' && request.method === 'GET') {
          return send(response, 200, { initialized: true });
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
            const transaction = { ...draft, id: `dev-${randomUUID()}` };
            transactions = [...transactions, transaction];
            return send(response, 201, { transaction });
          } catch {
            return send(response, 400, { error: { code: 'validation_error', message: '取引データを確認してください。' } });
          }
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
