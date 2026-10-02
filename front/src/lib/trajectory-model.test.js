import { expect, it } from 'vitest';
import transactionsFixture from '../data/september-transactions.json';
import timelineFixture from '../data/september-timeline.json';

const date = '2026-09-02';
const transactions = [
  { id: 'coffee', date, title: '朝のカフェ', type: 'expense', category: '食費', amount: 500, merchant: '店A', paymentMethod: 'cash', items: [{ name: 'ドリンク', amount: 500 }] },
  { id: 'train', date, title: '移動', type: 'expense', category: '交通', amount: 170, merchant: 'JR東日本', paymentMethod: 'e_money', items: [{ name: 'JR山手線 渋谷→恵比寿', amount: 170 }] },
  { id: 'grocery', date, title: '食材', type: 'expense', category: '食費', amount: 900, merchant: '店B', paymentMethod: 'cash', items: [{ name: '食材', amount: 900 }] },
];
const timeline = {
  places: {
    a: { name: '店A', address: '東京都渋谷区', coordinates: [139.7, 35.657], sourceUrl: 'https://example.com/a' },
    b: { name: '店B', address: '東京都渋谷区', coordinates: [139.711, 35.647], sourceUrl: 'https://example.com/b' },
  },
  days: [{ date, events: [
    { id: 'a', time: '09:00', placeId: 'a', transactionId: 'coffee' },
    { id: 'b', time: '12:00', placeId: 'b', transactionId: 'grocery' },
  ], legs: [{ fromEventId: 'a', toEventId: 'b', modeHint: 'train', transportTransactionId: 'train' }] }],
};

it('joins dated transactions and traffic evidence into a measured day', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const day = buildTrajectoryDays(transactions, timeline).get(date);
  expect(day).toBeDefined();
  expect(day.expenseTotal).toBe(1570);
  expect(day.stopCount).toBe(2);
  expect(day.events.map((event) => event.transaction?.id)).toEqual(['coffee', 'grocery']);
  expect(day.segments[0]).toMatchObject({ mode: 'train', coordinates: [[139.7, 35.657], [139.711, 35.647]] });
  expect(day.bounds).toEqual([139.7, 35.647, 139.711, 35.657]);
  expect(day.distanceKm).toBeGreaterThan(1);
});

it('builds 30 chronological Tokyo days with sourced places and matching purchases', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const days = buildTrajectoryDays(transactionsFixture, timelineFixture);
  expect(days.size).toBe(30);
  expect([...days.keys()]).toEqual(Array.from({ length: 30 }, (_, index) => `2026-09-${String(index + 1).padStart(2, '0')}`));
  for (const day of days.values()) {
    expect(day.events.length).toBeGreaterThanOrEqual(2);
    expect(day.events.map((event) => event.time)).toEqual([...day.events.map((event) => event.time)].sort());
    expect(day.segments).toHaveLength(day.events.length - 1);
    expect(day.bounds).toHaveLength(4);
    for (const event of day.events) {
      expect(event.place.sourceUrl).toMatch(/^https:\/\//);
      expect(event.place.coordinates[0]).toBeGreaterThan(139.4);
      expect(event.place.coordinates[0]).toBeLessThan(140.1);
      expect(event.place.coordinates[1]).toBeGreaterThan(35.4);
      expect(event.place.coordinates[1]).toBeLessThan(35.9);
      if (event.transaction) {
        expect(event.transaction.date).toBe(day.date);
        if (event.transaction.category !== '交通') expect(event.transaction.merchant).toBe(event.place.name);
        expect(event.transaction.items.length).toBeGreaterThan(0);
      }
    }
  }
  expect(days.get('2026-09-02').modes).toContain('train');
  expect(days.get('2026-09-01').modes).toContain('walk_estimated');
  expect(days.get('2026-09-05').events.some((event) => event.transaction?.id.endsWith('-pass'))).toBe(false);
  expect(days.get('2026-09-15').events.some((event) => event.transaction?.id.endsWith('-rent'))).toBe(false);
});

it('rejects unknown, cross-date, and duplicate references', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const copy = () => structuredClone(timeline);
  const unknown = copy();
  unknown.days[0].events[0].transactionId = 'missing';
  expect(() => buildTrajectoryDays(transactions, unknown)).toThrow(/missing/);
  const crossDate = copy();
  crossDate.days[0].events[0].transactionId = 'yesterday';
  expect(() => buildTrajectoryDays([...transactions, { ...transactions[0], id: 'yesterday', date: '2026-09-01' }], crossDate)).toThrow(/date|日付/i);
  const duplicateEvent = copy();
  duplicateEvent.days[0].events[1].id = 'a';
  expect(() => buildTrajectoryDays(transactions, duplicateEvent)).toThrow(/duplicate|重複/i);
  expect(() => buildTrajectoryDays([...transactions, transactions[0]], timeline)).toThrow(/duplicate|重複/i);
});

it('rejects transport without matching fare evidence and classifies unsupported legs as inferred', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const missingFare = structuredClone(timeline);
  delete missingFare.days[0].legs[0].transportTransactionId;
  expect(() => buildTrajectoryDays(transactions, missingFare)).toThrow(/transport|fare|交通/i);
  const wrongFare = structuredClone(timeline);
  wrongFare.days[0].legs[0].transportTransactionId = 'coffee';
  expect(() => buildTrajectoryDays(transactions, wrongFare)).toThrow(/transport|fare|交通/i);
  const inferred = structuredClone(timeline);
  delete inferred.days[0].legs[0].modeHint;
  expect(buildTrajectoryDays(transactions, inferred).get(date).segments[0].mode).toBe('inferred');
});
