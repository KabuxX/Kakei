import {expect, it} from 'vitest';
import {budgetUsage, isValidBudget, parseBudgetFields, sumBudget} from './budget.js';

const values = {'食費':60000,'住まい':90000,'日用品':25000,'交通':25000,'娯楽':30000,'その他':20000};
it('derives finite usage and excess for zero and exceeded budgets', () => {
  expect(budgetUsage(0,0)).toEqual({percent:0,over:false,excess:0});
  expect(budgetUsage(300,0)).toEqual({percent:100,over:true,excess:300});
  expect(budgetUsage(150,100)).toEqual({percent:100,over:true,excess:50});
  expect(budgetUsage(25,100)).toEqual({percent:25,over:false,excess:0});
  expect(sumBudget(values)).toBe(250000);
  expect(sumBudget(Object.fromEntries(Object.keys(values).map(n=>[n,999999999])))).toBe(5999999994);
});
it('rejects invalid input without treating blank amounts as zero', () => {
  const fields = Object.fromEntries(Object.entries(values).map(([n,v])=>[n,String(v)]));
  expect(parseBudgetFields({...fields,'食費':' 0 '})).toEqual({categories:{...values,'食費':0},errors:{}});
  for(const text of ['', '-1', '1.5', '1000000000', 'abc', '1e3']) {
    const result=parseBudgetFields({...fields,'食費':text});
    expect(result.categories).toBeNull();
    expect(result.errors['食費']).toBeTruthy();
  }
  for(const value of [null,[],{}, {...values,'食費':true}, {...values,'食費':'100'}, {...values,'未知':1}]) expect(isValidBudget(value)).toBe(false);
  expect(isValidBudget({...values,'食費':999999999})).toBe(true);
});
