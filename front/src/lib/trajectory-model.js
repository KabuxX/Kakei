import bbox from '@turf/bbox';
import length from '@turf/length';
import { featureCollection, lineString, point } from '@turf/helpers';
import { transactionCalendarDate } from './transaction-datetime.js';

function checkPlace(placeId, place) {
  if(place?.provider==='google'){
    if(!place.name||place.placeEvidence!=='google_places'||!/^[A-Za-z0-9_-]{1,512}$/.test(place.providerPlaceId||''))throw new Error(`Place ${placeId} needs a valid Google reference`);
    if(place.coordinates==null)return;
  }
  if (!place || !place.name || (!['user','google_places'].includes(place.placeEvidence) && (!place.address || !/^https:\/\//.test(place.sourceUrl || '')))) {
    throw new Error(`Place ${placeId} needs a name, address, and source URL`);
  }
  const [longitude, latitude] = place.coordinates || [];
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)
    || longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) {
    throw new Error(`Place ${placeId} needs valid coordinates`);
  }
}

function matchTransaction(transactionId, transactionsById, date) {
  const transaction = transactionsById.get(transactionId);
  if (!transaction) return null;
  if (transactionCalendarDate(transaction.date) !== date) throw new Error(`Transaction ${transactionId} has a different date`);
  return transaction;
}

function buildTrajectoryDays(transactions, timeline) {
  const transactionsById = new Map();
  const transactionsByDate = new Map();
  for (const transaction of transactions) {
    if (transactionsById.has(transaction.id)) throw new Error(`Duplicate transaction ${transaction.id}`);
    transactionsById.set(transaction.id, transaction);
    const date = transactionCalendarDate(transaction.date);
    const dated = transactionsByDate.get(date) || [];
    dated.push(transaction);
    transactionsByDate.set(date, dated);
  }

  for (const [placeId, place] of Object.entries(timeline.places)) checkPlace(placeId, place);
  const result = new Map();
  const eventIds = new Set();
  for (const day of timeline.days) {
    if (result.has(day.date)) throw new Error(`Duplicate day ${day.date}`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || !Number.isFinite(Date.parse(day.date))
      || new Date(day.date).toISOString().slice(0, 10) !== day.date) throw new Error(`Invalid date ${day.date}`);
    if (!Array.isArray(day.events)) throw new Error(`Day ${day.date} needs events`);
    const events = day.events.map((event) => {
      if (eventIds.has(event.id)) throw new Error(`Duplicate event ${event.id}`);
      eventIds.add(event.id);
      const place = timeline.places[event.placeId] || { name: '地点未確定', address: null, sourceUrl: null, coordinates: null, placeEvidence: 'unknown' };
      if (!(event.time === null && event.timeEvidence === 'unknown') && !/^([01]\d|2[0-3]):[0-5]\d$/.test(event.time)) throw new Error(`Invalid time ${event.time}`);
      const transaction = event.transactionId
        ? matchTransaction(event.transactionId, transactionsById, day.date)
        : null;
      return { ...event, place, transaction, transactionMissing: !!event.transactionId && !transaction, coordinates: event.locationStatus === 'needs_review' ? null : place.coordinates };
    });
    const knownTimes = events.filter(event => event.time !== null);
    if (knownTimes.some((event, index) => index > 0 && event.time < knownTimes[index - 1].time)) {
      throw new Error(`Day ${day.date} events are not chronological`);
    }
    if (!Array.isArray(day.legs)) throw new Error(`Day ${day.date} needs legs`);
    const segments = day.legs.map((leg, index) => {
      const fromIndex = events.findIndex((event) => event.id === leg.fromEventId);
      const from = events[fromIndex];
      const to = events[fromIndex + 1];
      if (!from || !to || leg.toEventId !== to.id) {
        throw new Error(`Day ${day.date} leg ${index + 1} does not connect consecutive events`);
      }
      let mode = 'inferred';
      let transportTransaction = null;
      if (leg.modeHint === 'walk') mode = 'walk_estimated';
      else if (leg.modeHint === 'train' || leg.modeHint === 'bus') {
        if (!leg.transportTransactionId && !['user','inferred'].includes(leg.modeEvidence)) throw new Error(`Leg ${index + 1} needs transport fare evidence`);
        transportTransaction = leg.transportTransactionId ? matchTransaction(leg.transportTransactionId, transactionsById, day.date) : null;
        if (transportTransaction && transportTransaction.category !== '交通') {
          throw new Error(`Leg ${index + 1} has no matching transport fare item`);
        }
        mode = leg.modeHint;
      } else if (leg.modeHint !== undefined) {
        throw new Error(`Unsupported mode ${leg.modeHint}`);
      }
      const via = (leg.viaPlaceIds || []).map((placeId) => {
        const place = timeline.places[placeId];
        return place?.coordinates || null;
      });
      const points = [from.coordinates, ...via, to.coordinates];
      const coordinates = points.every(Boolean) ? points : null;
      return {
        id: `${from.id}-${to.id}`,
        stageNumber: index + 1,
        fromEventId: from.id,
        toEventId: to.id,
        coordinates,
        mode,
        modeEvidence: leg.modeEvidence || 'legacy',
        modeEvidenceNote: leg.modeEvidenceNote,
        transportTransaction,
        distanceKm: coordinates ? length(lineString(coordinates)) : null,
      };
    });
    const features = [...segments.filter(s => s.coordinates).map((segment) => lineString(segment.coordinates)), ...events.filter(e => e.coordinates).map((event) => point(event.coordinates))];
    result.set(day.date, {
      date: day.date,
      events,
      segments,
      expenseTotal: (transactionsByDate.get(day.date) || [])
        .filter((transaction) => transaction.type === 'expense')
        .reduce((sum, transaction) => sum + transaction.amount, 0),
      stopCount: events.length,
      unconfirmedLocationCount: events.filter(e=>e.locationStatus==='needs_review').length,
      distanceIncomplete: segments.some(s=>!s.coordinates),
      hasEstimatedCoordinates: events.some(e=>e.coordinates&&e.place.coordinateEvidence?.status==='estimated')||day.legs.some(l=>(l.viaPlaceIds||[]).some(id=>timeline.places[id]?.coordinateEvidence?.status==='estimated')),
      modes: [...new Set(segments.map((segment) => segment.mode))],
      distanceKm: segments.length && segments.every(s=>s.distanceKm===null) ? null : segments.reduce((sum, segment) => sum + (segment.distanceKm||0), 0),
      bounds: features.length ? bbox(featureCollection(features)) : null,
    });
  }
  return result;
}

export { buildTrajectoryDays };
