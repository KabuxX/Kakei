import mapboxgl from 'mapbox-gl';
export function attachEstimatedMarkers(map,events,Marker=mapboxgl.Marker){
 const markers=[];
 for(const event of events){
  const coords=event.coordinates;
  if(event.locationStatus==='needs_review'||event.place?.coordinateEvidence?.status!=='estimated'||!Array.isArray(coords)||coords.length!==2||!coords.every(Number.isFinite)||Math.abs(coords[0])>180||Math.abs(coords[1])>90)continue;
  const element=document.createElement('span');element.className='trajectory-estimated-ring';element.setAttribute('aria-hidden','true');element.style.pointerEvents='none';
  markers.push(new Marker({element}).setLngLat(coords).addTo(map));
 }
 return ()=>markers.forEach(marker=>marker.remove());
}
