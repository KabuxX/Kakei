import React from 'react';

export default function TrajectoryDeletion({command,before,after,referenceLabels}) {
  const remainingEvents=new Set((after?.events||[]).map(event=>event.id));
  const removedEvents=before.events.filter(event=>!remainingEvents.has(event.id));
  const removedLegs=before.legs.filter(leg=>!(after?.legs||[]).some(next=>next.fromEventId===leg.fromEventId&&next.toEventId===leg.toEventId));
  const eventLabel=event=>`訪問 ${before.events.findIndex(saved=>saved.id===event.id)+1} · ${event.time||'時刻不明'} · ${referenceLabels[event.placeId]||'保存済み地点'}`;
  const endpointLabel=id=>{
    const event=before.events.find(event=>event.id===id);
    return event?eventLabel(event):'保存済み訪問';
  };
  return <section className="agent-change">
    <h3>{{day:'一日の軌跡を削除',event:'訪問を削除',leg:'移動区間を削除'}[command.identity.kind]}</h3>
    <p>{command.identity.date} · 訪問{removedEvents.length}件、移動{removedLegs.length}区間を削除します。</p>
    <div className="agent-diff">
      <div>
        {removedEvents.length>0&&<section aria-label="削除する訪問"><h4>削除する訪問</h4><ul>{removedEvents.map(event=><li key={event.id}>{eventLabel(event)}</li>)}</ul></section>}
        {removedLegs.length>0&&<section aria-label="削除する移動区間"><h4>削除する移動区間</h4><ul>{removedLegs.map(leg=><li key={`${leg.fromEventId}:${leg.toEventId}`}>{endpointLabel(leg.fromEventId)} → {endpointLabel(leg.toEventId)}</li>)}</ul></section>}
      </div>
      <div><h4>削除後</h4>{after?<p>削除後は訪問{after.events.length}件、移動{after.legs.length}区間が残ります。</p>:<p>この日の軌跡はなくなります。</p>}
        {command.identity.kind==='event'&&<p>残った訪問間に移動区間は自動生成しません。</p>}
        <p>取引と共有地点はそのまま残ります。</p>
      </div>
    </div>
  </section>;
}
