import {ApiError, request} from './api.js';
import {isValidBudget} from './budget.js';

function readResult(result) {
  if (!isValidBudget(result?.categories)) {
    throw new ApiError(200, {code: 'invalid_response', message: '予算データを確認できませんでした。もう一度お試しください。'});
  }
  return result.categories;
}

export async function loadBudget(fetchImpl = fetch) {
  return readResult(await request('GET', '/api/budget', undefined, fetchImpl));
}

export async function updateBudget(categories, fetchImpl = fetch) {
  return readResult(await request('PUT', '/api/budget', {categories}, fetchImpl));
}
