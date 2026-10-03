import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { listTrajectoryDates, loadTrajectoryDay } from './lib/api.js';
import { buildTrajectoryDays } from './lib/trajectory-model.js';
import { stageColor } from './lib/trajectory-display.js';
import '../trajectory.css';

const TrajectoryMap = lazy(() => import('./TrajectoryMap.jsx'));
const yen = new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY', maximumFractionDigits: 0 });
const dateLabel = (date) => `${Number(date.slice(5, 7))}月${Number(date.slice(8))}日`;
const evidenceLabel = {exact:'確定',estimated:'推定',unknown:'不明',legacy:'既存記録',fare:'交通費の記録',user:'ユーザー指定',inferred:'推定'};
const modeLabel = { train: '電車', bus: 'バス', walk_estimated: '徒歩（推定）', inferred: '移動（推定）' };

class MapErrorBoundary extends React.Component {
  state = { failed: false };

  static getDerivedStateFromError() { return { failed: true }; }

  render() {
    if (this.state.failed) return <div className="trajectory-map-loading" role="status">地図を読み込めませんでした。時系列はそのまま確認できます。</div>;
    return this.props.children;
  }
}

const EMPTY = [];
export default function Trajectory({ transactions = EMPTY, refreshKey = 0 }) {
  const [dates, setDates] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedEventId, setSelectedEventId] = useState(null);
  useEffect(() => {
    let active = true;
    setError('');
    listTrajectoryDates().then((saved) => {
      if (!active) return;
      setDates(saved);
      setSelectedDate((previous) => saved.includes(previous) ? previous : saved[0] || '');
    }).catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [retry, refreshKey]);
  useEffect(() => {
    if (!selectedDate) return undefined;
    let active = true;
    setTimeline(null);
    setError('');
    loadTrajectoryDay(selectedDate).then((saved) => { if (active) setTimeline(saved); })
      .catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [selectedDate, retry, refreshKey]);
  const model = useMemo(() => {
    if (!timeline) return {};
    try { return { day: buildTrajectoryDays(transactions, timeline).get(selectedDate) }; }
    catch (failure) { return { error: failure.message }; }
  }, [transactions, timeline, selectedDate]);
  const day = model.day;
  const dateIndex = dates?.indexOf(selectedDate) ?? -1;
  const changeDate = (date) => {
    if (!dates.includes(date)) return;
    setSelectedDate(date);
    setSelectedEventId(null);
  };

  return <div className="trajectory-page">
    <h1 id="trajectory-heading" className="sr-only" tabIndex="-1">生活軌跡</h1>
    {(error || model.error) && <div role="alert"><p>{error || model.error}</p><button className="secondary-button" onClick={() => setRetry((value) => value + 1)}>再読み込み</button></div>}
    {!dates && !error && <p role="status">記録日を読み込んでいます…</p>}
    {dates?.length === 0 && <p>軌跡の記録はまだありません。<a href="#agent">Agent Chat で作成する</a></p>}
    {dates?.length > 0 && <>
    <section className="trajectory-summary" aria-label="選択した日の概要">
      <div className="trajectory-date-row">
        <div>
          <p className="trajectory-section-label">選択した日</p>
          <strong className="trajectory-date-title">{selectedDate.slice(0, 4)}年{dateLabel(selectedDate)}</strong>
        </div>
        <div className="trajectory-date-controls">
          <button type="button" aria-label="前の記録日" onClick={() => changeDate(dates[dateIndex - 1])} disabled={dateIndex === 0}>‹</button>
          <label htmlFor="trajectory-date">表示する日付</label>
          <select id="trajectory-date" value={selectedDate} onChange={(event) => changeDate(event.target.value)}>
            {dates.map((date) => <option key={date} value={date}>{dateLabel(date)}</option>)}
          </select>
          <button type="button" aria-label="次の記録日" onClick={() => changeDate(dates[dateIndex + 1])} disabled={dateIndex === dates.length - 1}>›</button>
        </div>
      </div>
      {day && <div className="trajectory-stats">
        <div><span>訪問地点</span><strong>{day.stopCount}地点</strong></div>
        <div><span>記録された支出</span><strong>{yen.format(day.expenseTotal)}</strong></div>
        <div><span>地点間の直線距離</span><strong>約{day.distanceKm.toFixed(1)} km</strong></div>
      </div>}
      <p className="trajectory-summary-note">線と距離は地点間の概算です。実際に通った経路や移動距離ではありません。</p>
    </section>

    {!day && !error && !model.error && <p role="status">軌跡を読み込んでいます…</p>}
    {day && <div className="trajectory-content-grid">
      <section className="trajectory-map-panel" aria-labelledby="trajectory-map-heading">
        <div className="trajectory-panel-heading"><div><p className="trajectory-section-label">MAP</p><h2 id="trajectory-map-heading">一日の移動</h2></div><span>{dateLabel(selectedDate)}</span></div>
        <MapErrorBoundary>
          <Suspense fallback={<div className="trajectory-map-loading" role="status">地図を準備しています…</div>}>
            {day.bounds ? <TrajectoryMap day={day} selectedEventId={selectedEventId} onSelectEvent={setSelectedEventId} /> : <p>地図に表示する地点はありません。</p>}
          </Suspense>
        </MapErrorBoundary>
        <div className="trajectory-legend" aria-label="区間の色">
          {day.segments.map((segment) => <span className="trajectory-stage-key" key={segment.id} style={{ '--stage-color': stageColor(segment.stageNumber).hex }}><i className="trajectory-legend-line" aria-hidden="true" />区間{segment.stageNumber}</span>)}
          <span><i className="trajectory-legend-stop" aria-hidden="true" />訪問地点</span>
        </div>
      </section>

      <section className="trajectory-timeline-panel" aria-labelledby="trajectory-timeline-heading">
        <div className="trajectory-panel-heading"><div><p className="trajectory-section-label">TIMELINE</p><h2 id="trajectory-timeline-heading">時系列</h2></div><span>{day.events.length}件</span></div>
        <ol className="trajectory-timeline">
          {day.events.map((event, index) => {
            const before = day.segments.find(s => s.toEventId === event.id);
            return <li key={event.id}>
              {before && <p className="trajectory-leg-label" style={{ '--stage-color': stageColor(before.stageNumber).hex }}><i className="trajectory-legend-line" aria-hidden="true" />区間{before.stageNumber} · {modeLabel[before.mode]} · 約{before.distanceKm === null ? '距離不明' : `${before.distanceKm.toFixed(1)} km`} · {evidenceLabel[before.modeEvidence]}{before.modeEvidenceNote && `（${before.modeEvidenceNote}）`}</p>}
              <button className="trajectory-event" type="button" aria-pressed={selectedEventId === event.id} onClick={() => setSelectedEventId(event.id)}>
                <span className="trajectory-event-index">{index + 1}</span>
                <span className="trajectory-event-main"><span className="trajectory-event-time">{event.time || '時刻不明'} · {evidenceLabel[event.timeEvidence || 'legacy']}</span>{event.timeEvidenceNote && <small>{event.timeEvidenceNote}</small>}<strong>{event.place.name}</strong><small>{event.place.address || '住所未登録'}</small>{event.transactionMissing && <small>関連取引は見つかりません</small>}
                  {event.transaction && <span className="trajectory-purchase">{event.transaction.title} · {yen.format(event.transaction.amount)}<span>{event.transaction.items?.map((item) => item.name).join('・')}</span></span>}
                </span>
              </button>
              <p className="trajectory-source">{event.place.sourceUrl && <a href={event.place.sourceUrl} target="_blank" rel="noreferrer">地点の出典を見る<span className="sr-only">（新しいタブ）</span></a>}{event.place.attribution && <span> · {event.place.attribution}</span>}{event.place.placeEvidence === 'user' && <span>ユーザー指定の座標</span>}</p>
            </li>;
          })}
        </ol>
        {!day.events.length && <p>この日の訪問地点はまだありません。</p>}
      </section>
    </div>}
    </>}
  </div>;
}
