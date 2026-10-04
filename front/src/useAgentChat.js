import {useEffect, useRef, useState} from 'react';
import * as api from './lib/agent-api.js';

const emptyDraft = {text:'', receipt:null, retry:null};

// Lives at the app boundary so route and conversation changes retain drafts.
export function useAgentChat(enabled) {
  const [status,setStatus]=useState(null), [threads,setThreads]=useState([]), [thread,setThread]=useState(null);
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [drafts,setDrafts]=useState({});
  const [outgoing,setOutgoing]=useState({});
  const loaded=useRef(false), locked=useRef(false);
  const key=thread?.id||'new';
  const draft=drafts[key]||emptyDraft;
  const localMessages=outgoing[key]||[];
  const messages=[...(thread?.messages||[]),...localMessages.filter(m=>!thread?.messages?.some(saved=>saved.clientMessageId===m.clientMessageId))];
  const sending=localMessages.some(m=>m.state==='sending');
  const updateOutgoing=(target,message)=>setOutgoing(current=>({...current,[target]:[...(current[target]||[]).filter(m=>m.id!==message.id),message]}));
  const patchDraft=(changes, target=key)=>setDrafts(current=>({...current,[target]:{...(current[target]||emptyDraft),...changes}}));
  const load=async()=>{
    setLoading(true);setError('');
    try {const [s,t]=await Promise.all([api.status(),api.listThreads()]);setStatus(s);setThreads(t);}
    catch(e){setError(e.message||'会話を読み込めませんでした。');}
    finally{setLoading(false);}
  };
  useEffect(()=>{if(enabled&&!loaded.current){loaded.current=true;load();}},[enabled]);
  const act=async(fn)=>{
    if(busy||locked.current)return false;
    locked.current=true;setBusy(true);setError('');
    try{await fn();return true;}
    catch(e){setError(e.message||'通信できませんでした。再送できます。');return false;}
    finally{locked.current=false;setBusy(false);}
  };
  const ensureThread=async()=>{
    if(thread)return thread;
    const current=await api.createThread();
    setThread({...current,messages:[],proposals:[]});
    setThreads(items=>[current,...items]);
    setDrafts(items=>({...items,[current.id]:items.new||emptyDraft,new:emptyDraft}));
    setOutgoing(items=>({...items,[current.id]:items.new||[],new:[]}));
    return current;
  };
  const send=()=>{
    if(!draft.text.trim()||!status?.available)return Promise.resolve(false);
    let completion;
    return act(async()=>{
      const body=draft.retry?.text===draft.text&&draft.retry?.receiptId===draft.receipt?.id?draft.retry:
        {clientMessageId:crypto.randomUUID(),text:draft.text,...(draft.receipt?{receiptId:draft.receipt.id}:{})};
      const message={id:`local:${body.clientMessageId}`,clientMessageId:`user:${body.clientMessageId}`,role:'user',text:body.text,state:'sending'};
      let target=key;
      updateOutgoing(target,message);
      patchDraft({...emptyDraft,retry:body},target);
      try {
        const current=await ensureThread();target=current.id;
        completion=await api.sendMessage(target,body);
        setOutgoing(items=>({...items,[target]:(items[target]||[]).filter(m=>m.id!==message.id)}));
        patchDraft(emptyDraft,target);
      } catch(e) {
        updateOutgoing(target,{...message,state:'failed'});
        patchDraft({...draft,retry:body},target);
        throw e;
      }
      // A completed response is authoritative even if subsequent reads fail.
      if(completion?.message)setThread(current=>({...current,messages:[...(current?.messages||[]).filter(m=>m.clientMessageId!==message.clientMessageId),{...message,id:message.id,state:'complete'},completion.message],proposals:completion.proposal?[...(current?.proposals||[]),completion.proposal]:(current?.proposals||[])}));
      try {setThread(await api.getThread(target));} catch(e){setError(e.message||'会話の表示を更新できませんでした。');}
      // A sidebar refresh failure must not turn a completed message into a retry.
      try {setThreads(await api.listThreads());} catch(e){setError(e.message||'会話一覧を更新できませんでした。');}
    }).then(ok=>ok?(completion||true):false);
  };
  const select=id=>act(async()=>{setThread(id?await api.getThread(id):null);});
  const upload=file=>file&&act(async()=>{
    const current=await ensureThread();
    const receipt=await api.uploadReceipt(current.id,file);
    patchDraft({receipt:{...receipt,name:file.name},text:draft.text.trim()?draft.text:'このレシートを読み取ってください。'},current.id);
  });
  const removeThread=id=>{
    if(!window.confirm('会話と未保存の変更案を削除しますか？ 保存済みの取引は残ります。'))return Promise.resolve(false);
    return act(async()=>{
      await api.deleteThread(id);
      if(thread?.id===id)setThread(null);
      setDrafts(items=>{const next={...items};delete next[id];return next;});
      setOutgoing(items=>{const next={...items};delete next[id];return next;});
      setThreads(await api.listThreads());
    });
  };
  const change=proposal=>setThread(current=>({...current,proposals:current.proposals.map(p=>p.id===proposal.id?proposal:p)}));
  const proposed=proposal=>setThread(current=>({...current,proposals:[...current.proposals,proposal]}));
  return {status,threads,thread,messages,sending,busy,setBusy,loading,error,draft,load,send,select,upload,removeThread,change,proposed,
    prefillMessage:text=>setDrafts(current=>{const prior=current[key]||emptyDraft;return {...current,[key]:{...prior,text:[prior.text,text].filter(Boolean).join('\n')}};}),
    setText:text=>patchDraft({text}),removeReceipt:()=>patchDraft({receipt:null})};
}
