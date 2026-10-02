import { expect, it } from 'vitest';
import * as helpers from './transaction-datetime.js';

it('round_trips_local_datetime_without_timezone_shift', () => {
  const local = new Date(2026, 9, 3, 9, 17, 48);

  expect(helpers.dateTimeLocalValue(local)).toBe('2026-10-03T09:17');
  expect(helpers.transactionCalendarDate('2026-10-03T09:17')).toBe('2026-10-03');
  expect(helpers.transactionMonthKey('2026-10-03T09:17')).toBe('2026-10');
  expect(helpers.formatTransactionDate('2026-10-03T09:17')).toBe('2026年10月3日 09:17');
  expect(helpers.formatTransactionDate('2026-10-03')).toBe('2026年10月3日');
});

it('validates a real date and an in-range local minute', () => {
  expect(helpers.isValidTransactionDateTime('2026-10-03T09:17')).toBe(true);
  expect(helpers.isValidTransactionDateTime('2026-02-30T09:17')).toBe(false);
  expect(helpers.isValidTransactionDateTime('2026-10-03T24:00')).toBe(false);
  expect(helpers.isValidTransactionDateTime('2026-10-03T09:17:00')).toBe(false);
});

it('assigns stable estimated minutes to legacy mock records', () => {
  expect(typeof helpers.assignEstimatedTransactionDatetimes).toBe('function');
  const records = [
    { id: 'c', date: '2026-10-03' },
    { id: 'a', date: '2026-10-03' },
    { id: 'b', date: '2026-10-03' },
  ];

  const result = helpers.assignEstimatedTransactionDatetimes(records);

  expect(Object.fromEntries(result.map(({ id, date }) => [id, date]))).toEqual({
    a: '2026-10-03T11:30',
    b: '2026-10-03T15:00',
    c: '2026-10-03T18:30',
  });
  expect(result.every((record) => record.timeEstimated)).toBe(true);
  expect(helpers.assignEstimatedTransactionDatetimes(records)).toEqual(result);
  expect(records.every((record) => record.date === '2026-10-03')).toBe(true);
});
