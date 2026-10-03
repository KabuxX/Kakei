import React, { useEffect, useMemo, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { stageColor } from './lib/trajectory-display.js';
import 'mapbox-gl/dist/mapbox-gl.css';

function layersFor(day, selectedEventId, onSelectEvent) {
  return [
    new PathLayer({
      id: 'trajectory-paths',
      data: day.segments,
      getPath: (segment) => segment.coordinates,
      getColor: (segment) => stageColor(segment.stageNumber).rgb,
      getWidth: 6,
      widthUnits: 'pixels',
      jointRounded: true,
      capRounded: true,
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
  ];
}

export default function TrajectoryMap({ day, selectedEventId, onSelectEvent }) {
  const mapDay = useMemo(() => ({...day, events: day.events.every(e => e.coordinates) ? day.events : day.events.filter(e => e.coordinates), segments: day.segments.every(s => s.coordinates) ? day.segments : day.segments.filter(s => s.coordinates)}), [day]);
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
        style: 'mapbox://styles/mapbox/standard',
        config: { basemap: { font: 'Noto Sans CJK JP' } },
        language: 'ja',
        localIdeographFontFamily: false,
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
    overlayRef.current.setProps({ layers: layersFor(mapDay, selectedEventId, onSelectEvent) });
  }, [mapDay, selectedEventId, onSelectEvent, issue]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || issue || !day.bounds) return undefined;
    const markers = [];
    day.events.forEach((event, index) => {
      if (!event.coordinates) return;
      const element = document.createElement('span');
      element.className = 'trajectory-map-stop-number';
      element.textContent = String(index + 1);
      element.setAttribute('aria-hidden', 'true');
      markers.push(new mapboxgl.Marker({ element }).setLngLat(event.coordinates).addTo(map));
    });
    return () => {
      markers.forEach((marker) => marker.remove());
    };
  }, [day, issue]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || issue || !day.bounds) return undefined;
    const [west, south, east, north] = day.bounds;
    const fitDay = () => {
      const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      map.fitBounds([[west, south], [east, north]], {
        padding: 56,
        maxZoom: 15,
        duration: reduceMotion ? 0 : 400,
      });
    };
    fitDay();
    map.on('resize', fitDay);
    return () => map.off('resize', fitDay);
  }, [day, issue]);

  const message = !token ? 'Mapbox の公開トークンを設定すると地図を表示できます。時系列はそのまま確認できます。' : issue;
  return <div className="trajectory-map-frame" role="region" aria-label={`${day.date} の推定移動地図`} aria-describedby="trajectory-map-description">
    <p id="trajectory-map-description" className="sr-only">地点と直線で示した推定経路です。地点は下の時系列一覧からも選べます。</p>
    {message ? <div className="trajectory-map-message" role="status">{message}</div> : null}
    <div ref={containerRef} className="trajectory-map-canvas" aria-hidden="true" hidden={Boolean(message)} />
  </div>;
}
