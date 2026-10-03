import React, { useEffect, useState } from 'react';
import { ApiError, loadTrajectoryDay } from './lib/api.js';

function mapHref(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length !== 2) return null;
  const [longitude, latitude] = coordinates;
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) return null;
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=18/${latitude}/${longitude}`;
}

export default function TransactionAddress({ transactionId, date }) {
  const [places, setPlaces] = useState([]);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setPlaces([]);
    setFailed(false);
    loadTrajectoryDay(date).then((timeline) => {
      if (!active) return;
      const ids = new Set(timeline.days.filter(day => day.date === date)
        .flatMap(day => day.events || []).filter(event => event.transactionId === transactionId).map(event => event.placeId));
      setPlaces([...ids].map(id => ({ ...timeline.places[id], id }))
        .filter(place => typeof place.address === 'string' && place.address.trim()));
    }).catch((error) => {
      if (active && !(error instanceof ApiError && error.status === 404)) setFailed(true);
    });
    return () => { active = false; };
  }, [transactionId, date, attempt]);

  if (!failed && !places.length) return null;
  return <>
    <dt className="detail-address-label">住所</dt>
    <dd className="detail-address">
      {failed ? <div role="alert"><p>住所を読み込めませんでした。</p><button className="secondary-button" type="button" onClick={() => setAttempt(value => value + 1)}>住所を再読み込み</button></div>
        : places.map(place => <div key={place.id} className="detail-address-place">
          {places.length > 1 && <strong>{place.name}</strong>}
          <p>{place.address}</p>
          {mapHref(place.coordinates) && <a className="detail-map-link" href={mapHref(place.coordinates)} target="_blank" rel="noopener noreferrer">地図で見る<span className="sr-only">（新しいタブで開く）</span></a>}
        </div>)}
    </dd>
  </>;
}
