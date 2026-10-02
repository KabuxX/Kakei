import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import 'mapbox-gl/dist/mapbox-gl.css';

function layersFor(day, selectedEventId, onSelectEvent) {
  return [
    new PathLayer({
      id: 'trajectory-paths',
      data: day.segments,
      getPath: (segment) => segment.coordinates,
      getColor: (segment) => segment.mode === 'train' || segment.mode === 'bus' ? [65, 94, 238] : [31, 32, 37],
      getWidth: 5,
      widthUnits: 'pixels',
      rounded: true,
    }),
    new ScatterplotLayer({
      id: 'trajectory-stops',
      data: day.events,
      getPosition: (event) => event.coordinates,
      getFillColor: (event) => event.id === selectedEventId ? [255, 171, 148] : [255, 255, 255],
      getLineColor: [31, 32, 37],
      stroked: true,
      getLineWidth: 2,
      lineWidthUnits: 'pixels',
      getRadius: (event) => event.id === selectedEventId ? 11 : 9,
      updateTriggers: { getFillColor: selectedEventId, getRadius: selectedEventId },
      radiusUnits: 'pixels',
      pickable: true,
      onClick: ({ object }) => { if (object) onSelectEvent(object.id); },
    }),
    new TextLayer({
      id: 'trajectory-stop-numbers',
      data: day.events.map((event, index) => ({ ...event, number: String(index + 1) })),
      getPosition: (event) => event.coordinates,
      getText: (event) => event.number,
      getColor: [31, 32, 37],
      getSize: 13,
      sizeUnits: 'pixels',
      fontWeight: 600,
      pickable: false,
    }),
  ];
}

export default function TrajectoryMap({ day, selectedEventId, onSelectEvent }) {
  const token = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const [issue, setIssue] = useState('');

  useEffect(() => {
    if (!token) return undefined;
    if (!mapboxgl.supported()) {
      setIssue('この端末では WebGL を利用できないため、地図を表示できません。');
      return undefined;
    }
    try {
      const map = new mapboxgl.Map({
        container: containerRef.current,
        accessToken: token,
        style: 'mapbox://styles/mapbox/light-v11',
        center: [139.703, 35.658],
        zoom: 12,
        attributionControl: true,
      });
      const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
      map.addControl(overlay);
      map.on('error', () => setIssue('地図を読み込めませんでした。時系列は下の一覧から確認できます。'));
      mapRef.current = map;
      overlayRef.current = overlay;
      return () => {
        mapRef.current = null;
        overlayRef.current = null;
        map.remove();
      };
    } catch (_) {
      setIssue('地図を読み込めませんでした。時系列は下の一覧から確認できます。');
      return undefined;
    }
  }, []);

  useEffect(() => {
    if (!mapRef.current || !overlayRef.current || issue) return;
    overlayRef.current.setProps({ layers: layersFor(day, selectedEventId, onSelectEvent) });
  }, [day, selectedEventId, onSelectEvent, issue]);

  useEffect(() => {
    if (!mapRef.current || issue) return;
    const [west, south, east, north] = day.bounds;
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    mapRef.current.fitBounds([[west, south], [east, north]], {
      padding: 56,
      maxZoom: 15,
      duration: reduceMotion ? 0 : 400,
    });
  }, [day, issue]);

  const message = !token ? 'Mapbox の公開トークンを設定すると地図を表示できます。時系列はそのまま確認できます。' : issue;
  return <div className="trajectory-map-frame" role="region" aria-label={`${day.date} の推定移動地図`} aria-describedby="trajectory-map-description">
    <p id="trajectory-map-description" className="sr-only">地点と直線で示した推定経路です。地点は下の時系列一覧からも選べます。</p>
    {message ? <div className="trajectory-map-message" role="status">{message}</div> : null}
    <div ref={containerRef} className="trajectory-map-canvas" aria-hidden="true" hidden={Boolean(message)} />
  </div>;
}
