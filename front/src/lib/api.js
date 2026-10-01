  const storageKey = 'kakei-transactions-v1';

  class ApiError extends Error {
    constructor(status, detail = {}) {
      super(detail.message || 'サーバーとの通信に失敗しました。');
      this.name = 'ApiError';
      this.status = status;
      this.code = detail.code || 'request_failed';
      this.field = detail.field || null;
    }
  }

  async function request(method, path, body, fetchImpl = fetch) {
    const options = { method };
    if (body !== undefined) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    const response = await fetchImpl(path, options);
    if (response.status === 204) return null;
    const result = await response.json();
    if (!response.ok) throw new ApiError(response.status, result?.error);
    return result;
  }

  async function listTransactions(fetchImpl = fetch) {
    const result = await request('GET', '/api/transactions', undefined, fetchImpl);
    if (!Array.isArray(result?.transactions)) throw new ApiError(200, { code: 'invalid_response', message: '取引データを読み込めませんでした。' });
    return result.transactions;
  }

  async function loadInitialTransactions({ fetchImpl = fetch, storage, sampleFactory }) {
    const status = await request('GET', '/api/status', undefined, fetchImpl);
    if (typeof status?.initialized !== 'boolean') throw new ApiError(200, { code: 'invalid_response', message: 'サーバーの状態を確認できませんでした。' });
    if (!status.initialized) {
      const raw = storage.getItem(storageKey);
      const records = raw === null ? sampleFactory() : JSON.parse(raw);
      if (!Array.isArray(records)) throw new Error('保存済みの取引データは配列ではありません。');
      try {
        await request('POST', '/api/initialize', { transactions: records }, fetchImpl);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 409 && error.code === 'already_initialized')) throw error;
      }
    }
    return listTransactions(fetchImpl);
  }

  async function addTransaction(draft, fetchImpl = fetch) {
    const result = await request('POST', '/api/transactions', draft, fetchImpl);
    if (!result?.transaction || typeof result.transaction.id !== 'string') {
      throw new ApiError(201, { code: 'invalid_response', message: '保存結果を確認できませんでした。' });
    }
    return result.transaction;
  }

  async function removeTransaction(id, fetchImpl = fetch) {
    await request('DELETE', `/api/transactions/${encodeURIComponent(id)}`, undefined, fetchImpl);
  }

  async function removeSamples(fetchImpl = fetch) {
    const result = await request('DELETE', '/api/samples', undefined, fetchImpl);
    if (!Number.isInteger(result?.deletedCount)) {
      throw new ApiError(200, { code: 'invalid_response', message: '削除結果を確認できませんでした。' });
    }
    return result.deletedCount;
  }

export { ApiError, listTransactions, loadInitialTransactions, addTransaction, removeTransaction, removeSamples };
