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

it('test_arbitrary_date_and_global_place', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const changed = structuredClone(timeline);
  changed.days[0].date = '2027-01-04';
  changed.days[0].events.forEach((event) => { delete event.transactionId; });
  changed.days[0].legs = [{ fromEventId: 'a', toEventId: 'b' }];
  changed.places.a.coordinates = [-73.98, 40.75];
  changed.places.b.coordinates = [-73.97, 40.76];
  expect(buildTrajectoryDays([], changed).get('2027-01-04').stopCount).toBe(2);
});

it('test_empty_and_single_event_days', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const days = buildTrajectoryDays([], { places: timeline.places, days: [
    { date: '2027-01-01', events: [], legs: [] },
    { date: '2027-01-02', events: [{ id: 'one', time: '12:00', placeId: 'a' }], legs: [] },
  ] });
  expect(days.get('2027-01-01').bounds).toBeNull();
  expect(days.get('2027-01-02').bounds).toEqual([139.7, 35.657, 139.7, 35.657]);
  expect(days.get('2027-01-02').segments).toEqual([]);
});

it('joins dated transactions and traffic evidence into a measured day', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const day = buildTrajectoryDays(transactions, timeline).get(date);
  expect(day).toBeDefined();
  expect(day.expenseTotal).toBe(1570);
  expect(day.stopCount).toBe(2);
  expect(day.events.map((event) => event.transaction?.id)).toEqual(['coffee', 'grocery']);
  expect(day.segments[0]).toMatchObject({ mode: 'train', coordinates: [[139.7, 35.657], [139.711, 35.647]] });
  expect(day.segments[0].stageNumber).toBe(1);
  expect(day.bounds).toEqual([139.7, 35.647, 139.711, 35.657]);
  expect(day.distanceKm).toBeGreaterThan(1);
});

it('joins timestamped transactions to same-date events', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const timestamped = transactions.map((transaction, index) => ({
    ...transaction,
    date: `${date}T${['09:17', '10:30', '12:00'][index]}`,
  }));

  const day = buildTrajectoryDays(timestamped, timeline).get(date);

  expect(day.expenseTotal).toBe(1570);
  expect(day.events.map((event) => event.transaction?.id)).toEqual(['coffee', 'grocery']);
  expect(day.segments[0].transportTransaction.id).toBe('train');
  const wrongDay = structuredClone(timeline);
  wrongDay.days[0].events[0].transactionId = 'yesterday';
  expect(() => buildTrajectoryDays([
    ...timestamped,
    { ...timestamped[0], id: 'yesterday', date: '2026-09-01T18:40' },
  ], wrongDay)).toThrow(/date|日付/i);
});

it('builds 12 chronological Tokyo days with sourced places and matching purchases', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const days = buildTrajectoryDays(transactionsFixture, timelineFixture);
  expect(days.size).toBe(12);
  expect([...days.keys()]).toEqual(Array.from({ length: 12 }, (_, index) => `2026-09-${String(index + 19).padStart(2, '0')}`));
  for (const day of days.values()) {
    expect(day.events.length).toBeGreaterThanOrEqual(2);
    expect(day.events.map((event) => event.time)).toEqual([...day.events.map((event) => event.time)].sort());
    expect(day.segments).toHaveLength(day.events.length - 1);
    day.segments.forEach((segment, index) => {
      expect(segment.stageNumber).toBe(index + 1);
    });
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
  expect(Object.keys(timelineFixture.places)).toHaveLength(10);
  expect(timelineFixture.days.flatMap((day) => day.events)).toHaveLength(36);
  const legs = timelineFixture.days.flatMap((day) => day.legs);
  expect(legs).toHaveLength(24);
  expect(legs.filter((leg) => leg.modeHint === 'train')).toHaveLength(2);
  for (const day of timelineFixture.days) {
    for (const event of day.events) {
      expect(timelineFixture.places[event.placeId]).toBeDefined();
      if (event.transactionId) expect(transactionsFixture.find((record) => record.id === event.transactionId)?.date).toBe(day.date);
    }
    for (const leg of day.legs) {
      expect(day.events.some((event) => event.id === leg.fromEventId)).toBe(true);
      expect(day.events.some((event) => event.id === leg.toEventId)).toBe(true);
      for (const point of leg.viaPlaceIds || []) expect(timelineFixture.places[point]).toBeDefined();
      if (leg.transportTransactionId) expect(transactionsFixture.find((record) => record.id === leg.transportTransactionId)?.date).toBe(day.date);
      if (leg.modeHint === 'train') expect(leg.transportTransactionId).toBeTruthy();
    }
  }
  expect(days.get('2026-09-29').modes).toContain('train');
  expect(days.has('2026-09-02')).toBe(false);
});

it('rejects unknown, cross-date, and duplicate references', async () => {
  const { buildTrajectoryDays } = await import('./trajectory-model.js');
  const copy = () => structuredClone(timeline);
  const unknown = copy();
  unknown.days[0].events[0].transactionId = 'missing';
  expect(buildTrajectoryDays(transactions, unknown).get(date).events[0].transactionMissing).toBe(true);
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

it('keeps unknown times and unresolved places without fabricated map points',async()=>{
 const {buildTrajectoryDays}=await import('./trajectory-model.js');
 const timeline={places:{p:{name:'手動地点',address:null,sourceUrl:null,coordinates:[-73,40],placeEvidence:'user'}},days:[{date:'2027-01-04',events:[{id:'a',placeId:'p',time:null,timeEvidence:'unknown'},{id:'b',placeId:'unresolved',time:null,timeEvidence:'unknown'}],legs:[{fromEventId:'a',toEventId:'b',modeEvidence:'inferred',modeEvidenceNote:'経路は不明'}]}]};
 const day=buildTrajectoryDays([],timeline).get('2027-01-04');
 expect(day.events[0].time).toBeNull();expect(day.events[1].coordinates).toBeNull();
 expect(day.segments[0].distanceKm).toBeNull();expect(day.bounds).toEqual([-73,40,-73,40]);
});

it('keeps an unconfirmed middle visit without bridging its neighbours', async () => {
  const {buildTrajectoryDays}=await import('./trajectory-model.js');
  const modelTimeline=structuredClone(timelineFixture);
  const day=modelTimeline.days.find(d=>d.events.length===3);
  day.events[1].locationStatus='needs_review';
  const result=buildTrajectoryDays(transactionsFixture,modelTimeline).get(day.date);
  expect(result.events).toHaveLength(3);
  expect(result.events[1].coordinates).toBeNull();
  expect(result.segments.every(s=>s.coordinates===null)).toBe(true);
  expect(result.unconfirmedLocationCount).toBe(1);
  expect(result.distanceIncomplete).toBe(true);
});
it('keeps_visits_with_unavailable_coordinates_and_equal_times',async()=>{
 const {buildTrajectoryDays}=await import('./trajectory-model.js');
 const google={name:'店A',provider:'google',providerPlaceId:'fixture-a',placeEvidence:'google_places',address:null,sourceUrl:null,coordinates:null};
 const day=buildTrajectoryDays([],{places:{a:google,b:{...google,providerPlaceId:'fixture-b'}},days:[{date,events:[{id:'a',placeId:'a',time:'12:00',timeEvidence:'exact'},{id:'b',placeId:'b',time:'12:00',timeEvidence:'exact'}],legs:[{fromEventId:'a',toEventId:'b',modeEvidence:'inferred'}]}]}).get(date);
 expect(day.events).toHaveLength(2);expect(day.segments[0].distanceKm).toBeNull();expect(day.distanceKm).toBeNull();expect(day.bounds).toBeNull();
});
