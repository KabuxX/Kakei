import React from 'react';
export default function AgentTrajectoryResult({result,onOpenTrajectory}) {
 const {date,counts,excluded=[]}=result;
 const list=<ul>{excluded.map(item=><li key={item.transactionId}><strong>{item.label}</strong>{item.time&&<span> · {item.time}{item.timeEstimated?'（推定）':''}</span>}<p>{item.message}</p></li>)}</ul>;
 return <section className="agent-trajectory-result" aria-label={`${date}の軌跡作成結果`}>
  <h3>{date}の軌跡</h3><p className="agent-trajectory-counts">{counts.saved}件保存 · {counts.existing}件作成済み · {counts.excluded}件除外</p>
  {!!excluded.length&&(excluded.length>5?<details><summary>除外した訪問を表示（{excluded.length}件）</summary>{list}</details>:list)}
  {(counts.saved>0||counts.existing>0)&&<a className="secondary-button" href="#trajectory" onClick={()=>onOpenTrajectory?.(date)}>{date}の軌跡を開く</a>}
 </section>;
}
