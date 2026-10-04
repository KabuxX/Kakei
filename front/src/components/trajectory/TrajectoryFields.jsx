import React from 'react';
export default function TrajectoryFields({command,onChange}){
 const data=command.data;
 if(command.kind==='trajectory.delete')return <p>{command.identity.date} の削除対象を変更する場合はメッセージで伝えてください。</p>;
 if(command.identity.kind!=='day')return <p>この操作の修正内容はメッセージで伝えてください。</p>;
 const setEvent=(index,patch)=>onChange({...command,data:{...data,events:data.events.map((e,i)=>i===index?{...e,...patch}:e)}});
 const move=(index,step)=>{const events=[...data.events];[events[index],events[index+step]]=[events[index+step],events[index]];
  const legs=events.slice(1).map((e,i)=>data.legs.find(l=>l.fromEventId===events[i].id&&l.toEventId===e.id)||{fromEventId:events[i].id,toEventId:e.id,modeEvidence:'inferred',modeEvidenceNote:'ユーザーが指定した訪問順。移動経路・手段は未確認'});
  onChange({...command,data:{events,legs}});
 };
 return <fieldset><legend>{command.identity.date} の訪問順・時刻</legend>{data.events.map((e,i)=><div key={e.id} className="agent-event-edit"><strong>{i+1}. {e.placeId}</strong><div className="agent-fields"><label>時刻 {i+1}<input type="time" value={e.time||''} onChange={v=>setEvent(i,{time:v.target.value||null,timeEvidence:v.target.value?(e.timeEvidence==='unknown'?'estimated':e.timeEvidence):'unknown'})}/></label><label>時刻の根拠 {i+1}<select value={e.timeEvidence||'legacy'} onChange={v=>setEvent(i,{timeEvidence:v.target.value,...(v.target.value==='unknown'?{time:null}:{})})}>{['exact','estimated','unknown','legacy'].map((v,n)=><option key={v} value={v}>{['確定','推定','不明','既存記録'][n]}</option>)}</select></label><label>時刻の説明 {i+1}<input value={e.timeEvidenceNote||''} onChange={v=>setEvent(i,{timeEvidenceNote:v.target.value||null})}/></label></div><div className="agent-actions"><button className="secondary-button" type="button" disabled={i===0} onClick={()=>move(i,-1)}>訪問 {i+1} を前へ</button><button className="secondary-button" type="button" disabled={i===data.events.length-1} onClick={()=>move(i,1)}>訪問 {i+1} を後へ</button></div></div>)}</fieldset>;
}
