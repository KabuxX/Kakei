import {expect,it,vi} from 'vitest';
import {loadBudget,updateBudget} from './budget-api.js';
const categories={'食費':60000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000};
const response=body=>({ok:true,status:200,json:async()=>body});
it('reads and saves the complete category envelope',async()=>{
  const fetchImpl=vi.fn(async(path,options)=>{
    expect(path).toBe('/api/budget');
    if(options.method==='PUT')expect(JSON.parse(options.body)).toEqual({categories});
    return response({categories});
  });
  expect(await loadBudget(fetchImpl)).toEqual(categories);
  expect(await updateBudget(categories,fetchImpl)).toEqual(categories);
});
it('rejects malformed successful responses for both reads and writes',async()=>{
  for(const body of [{}, {categories:{'食費':1}}, {categories:{...categories,'食費':'100'}}]) {
    const fetchImpl=async()=>response(body);
    await expect(loadBudget(fetchImpl)).rejects.toThrow();
    await expect(updateBudget(categories,fetchImpl)).rejects.toThrow();
  }
});
