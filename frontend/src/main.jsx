import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
const API='/api';
function App(){
 const [docs,setDocs]=useState([]),[question,setQuestion]=useState(''),[answer,setAnswer]=useState(null),[busy,setBusy]=useState(false),[uploading,setUploading]=useState(false),[notice,setNotice]=useState(''),[progress,setProgress]=useState(0),[stage,setStage]=useState('');
 async function reload(){try{const r=await fetch(API+'/documents');if(!r.ok)throw Error('Backend unavailable');setDocs(await r.json())}catch(e){setNotice('Start PostgreSQL and FastAPI: '+e.message)}}
 useEffect(()=>{reload()},[]);
 async function upload(e){
  const f=e.target.files?.[0];if(!f)return;
  setUploading(true);setNotice('');setProgress(0);setStage('Uploading file');
  const form=new FormData();form.append('file',f);
  try{
   // XMLHttpRequest exposes genuine network upload progress.
   const job=await new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST',API+'/documents/jobs');
    xhr.upload.onprogress=event=>{
     if(event.lengthComputable){
      setProgress(Math.min(10,Math.round(event.loaded/event.total*10)));
     }
    };
    xhr.onload=()=>{
     let result;try{result=JSON.parse(xhr.responseText)}catch{reject(Error('Invalid server response'));return}
     if(xhr.status!==202){reject(Error(result.detail||'Upload failed'));return}
     resolve(result);
    };
    xhr.onerror=()=>reject(Error('Network error while uploading'));
    xhr.send(form);
   });
   setStage('Queued for indexing');setProgress(10);
   // Poll server-reported processing stages. No page refresh is required.
   let finalJob=null;
   for(let attempt=0;attempt<600;attempt++){
    const response=await fetch(API+'/documents/jobs/'+job.job_id,{cache:'no-store'});
    if(!response.ok)throw Error('Could not check indexing progress');
    const state=await response.json();
    setProgress(state.progress);setStage(state.stage);
    if(state.status==='completed'){finalJob=state;break}
    if(state.status==='failed')throw Error(state.error||'Indexing failed');
    await new Promise(resolve=>setTimeout(resolve,800));
   }
   if(!finalJob)throw Error('Indexing is taking too long; check the server');
   await reload();
   setNotice('Document indexed and ready to search');
  }catch(error){setNotice(error.message);setStage('Upload unsuccessful')}
  finally{setUploading(false);e.target.value=''}
 }
 async function ask(e){e.preventDefault();if(!question.trim())return;setBusy(true);setAnswer(null);setNotice('');try{const r=await fetch(API+'/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');setAnswer(d)}catch(e){setNotice(e.message)}finally{setBusy(false)}}
 return <div className="app"><aside><h1>🌿 BhoomiAI</h1><p>Land Research Workspace</p><div className="tag">STAGE 1 · LOCAL RAG</div><h3>Documents ({docs.length})</h3><label className="upload">{uploading?'Processing document...':'Upload PDF / TXT / MD'}<input type="file" accept=".pdf,.txt,.md" disabled={uploading} onChange={upload}/></label>{uploading&&<div className="upload-progress" role="status" aria-live="polite"><div className="progress-label">{stage} · {progress}%</div><div className="progress-track"><div className="progress-fill" style={{width:progress+'%'}} /></div></div>}{docs.map(d=><div className="doc" key={d.id}><strong>{d.filename}</strong><small>{d.chunks} chunks</small></div>)}{!docs.length&&<p>No documents yet. Upload the sample file.</p>}<footer>Free local model · Development only</footer></aside><main><header><div className="eyebrow">RESEARCH DISCOVERY</div><h2>Ask your land-governance documents</h2><p>Evidence-grounded answers with retrieved source passages.</p></header><section><form onSubmit={ask}><label htmlFor="question">Your research question</label><textarea id="question" rows={4} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="What issues affect land-record modernization?"/><button disabled={busy||!question.trim()}>{busy?'Searching...':'Ask BhoomiAI'}</button></form>{notice&&<div className="notice">{notice}</div>}{answer&&<article><h3>Research answer</h3><div className="answer">{answer.answer}</div><h3>Sources ({answer.sources.length})</h3>{answer.sources.map(s=><div className="source" key={s.chunk_id}><strong>[{s.ref}] {s.filename}</strong> · {s.page?'Page '+s.page:'Text source'}<p>{s.excerpt}</p></div>)}</article>}<p className="hint">Next: geo-aware retrieval, GIS maps and policy scenarios.</p></section></main></div>
}
createRoot(document.getElementById('root')).render(<App/>);
