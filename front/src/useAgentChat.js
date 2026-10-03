import {useEffect, useRef, useState} from 'react';
import * as api from './lib/agent-api.js';

const emptyDraft = {text:'', receipt:null, retry:null};

// Lives at the app boundary so route and conversation changes retain drafts.
export function useAgentChat(enabled) {
  const [status,setStatus]=useState(null), [threads,setThreads]=useState([]), [thread,setThread]=useState(null);
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [drafts,setDrafts]=useState({});
  const loaded=useRef(false), locked=useRef(false);
  const key=thread?.id||'new';
  const draft=drafts[key]||emptyDraft;
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
    return current;
  };
  const send=()=>{
    if(!draft.text.trim()||!status?.available)return Promise.resolve(false);
    return act(async()=>{
      const current=await ensureThread();
      const body=draft.retry?.text===draft.text&&draft.retry?.receiptId===draft.receipt?.id?draft.retry:
        {clientMessageId:crypto.randomUUID(),text:draft.text,...(draft.receipt?{receiptId:draft.receipt.id}:{})};
      patchDraft({retry:body},current.id);
      await api.sendMessage(current.id,body);
      patchDraft(emptyDraft,current.id);
      setThread(await api.getThread(current.id));setThreads(await api.listThreads());
    });
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
      setThreads(await api.listThreads());
    });
  };
  const change=proposal=>setThread(current=>({...current,proposals:current.proposals.map(p=>p.id===proposal.id?proposal:p)}));
  const proposed=proposal=>setThread(current=>({...current,proposals:[...current.proposals,proposal]}));
  return {status,threads,thread,busy,setBusy,loading,error,draft,load,send,select,upload,removeThread,change,proposed,
    setText:text=>patchDraft({text}),removeReceipt:()=>patchDraft({receipt:null})};
}
