import React,{useEffect,useState} from 'react';
import {API,apiFetch} from './api.js';

async function request(path,options){
 const res=await apiFetch(API+path,options);
 if(!res.ok){
  const d=await res.json().catch(()=>({detail:'Request failed'}));
  throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d));
 }
 return res;
}
function Download({path,label}){
 async function run(){
  try{
   const res=await request(path);
   const blob=await res.blob();
   const url=URL.createObjectURL(blob);
   const a=document.createElement('a');
   a.href=url;a.download=path.endsWith('template')?'indicator_template.csv':'land_indicators.csv';
   document.body.appendChild(a);a.click();a.remove();
   setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){window.alert(e.message)}
 }
 return <button type="button" onClick={run}>{label}</button>;
}
export default function AdvancedPage({user}){
 const [ready,setReady]=useState(null),[graph,setGraph]=useState(null),[error,setError]=useState('');
 const [csv,setCsv]=useState(null),[uploading,setUploading]=useState(false);
 const [query,setQuery]=useState({state:'Uttar Pradesh',district:'Ghaziabad',indicator:''});
 const [trend,setTrend]=useState(null),[working,setWorking]=useState(false);
 async function refresh(){
  const [a,b]=await Promise.all([
   request('/advanced/data-readiness').then(r=>r.json()),
   request('/advanced/provenance-graph').then(r=>r.json())
  ]);
  setReady(a);setGraph(b);
 }
 useEffect(()=>{refresh().catch(e=>setError(e.message))},[]);
 async function upload(e){
  e.preventDefault();if(!csv)return;setUploading(true);setError('');
  try{
   const body=new FormData();body.append('file',csv);
   const result=await request('/advanced/indicators/import-csv',{method:'POST',body}).then(r=>r.json());
   setError('Imported '+result.imported+' source-attributed observations. Check originals independently.');
   setCsv(null);await refresh();
  }catch(ex){setError(ex.message)}finally{setUploading(false)}
 }
 async function getTrend(e){
  e.preventDefault();setWorking(true);setError('');
  try{
   const p=new URLSearchParams(query);
   setTrend(await request('/advanced/indicators/trends?'+p).then(r=>r.json()));
  }catch(ex){setError(ex.message)}finally{setWorking(false)}
 }
 return <div className="advanced">
  <header><div className="eyebrow">DATA QUALITY · TRACEABLE EVIDENCE</div><h2>Data and Provenance</h2><p>Review evidence metadata, import sourced observations and inspect explicit research relationships.</p></header>
  {error&&<p className="hub-message" role="status">{error}</p>}
  <div className="hub-grid">
   <section className="hub-panel">
    <h3>Repository data readiness</h3>
    {ready?<><div className="hub-metrics">
     <div><strong>{ready.documents.total}</strong><small>Indexed documents</small></div>
     <div><strong>{ready.documents.missing_source_url}</strong><small>Documents missing source URLs</small></div>
     <div><strong>{ready.documents.missing_state_tag}</strong><small>Documents without state tags</small></div>
     <div><strong>{ready.evidence_notes.confirmed}</strong><small>Reviewed and confirmed notes</small></div>
    </div><h4>Locally entered indicator coverage</h4><table><thead><tr><th>Region</th><th>Years</th><th>Indicators</th><th>Observations</th></tr></thead><tbody>
     {ready.indicator_coverage.map((r,i)=><tr key={i}><td>{r.district}, {r.state}</td><td>{r.years}</td><td>{r.indicators}</td><td>{r.observations}</td></tr>)}
    </tbody></table><p className="hub-caution">{ready.warning}</p></>:<p>Loading repository metadata...</p>}
    <button type="button" onClick={()=>refresh().catch(e=>setError(e.message))}>Refresh readiness</button>
   </section>
   <section className="hub-panel">
    <h3>Source-attributed CSV import</h3>
    <p>Use the template to import published indicator observations. Source URLs and dataset names are mandatory; values are never generated automatically.</p>
    <div className="advanced-buttons"><Download path="/advanced/indicators/template" label="Download CSV template"/><Download path="/advanced/indicators/export" label="Export current indicators"/></div>
    {user.role==='admin'?<form onSubmit={upload}><label>Select CSV file (up to 2 MB and 1,000 rows)<input type="file" accept=".csv,text/csv" required onChange={e=>setCsv(e.target.files?.[0]||null)}/></label><button disabled={!csv||uploading}>{uploading?'Importing...':'Import observations'}</button></form>:<p className="small-muted">Only administrators can import indicators.</p>}
   </section>
   <section className="hub-panel">
    <h3>Historical indicator comparison</h3>
    <form onSubmit={getTrend}>
     {Object.keys(query).map(k=><label key={k}>{k[0].toUpperCase()+k.slice(1)}<input required value={query[k]} onChange={e=>setQuery({...query,[k]:e.target.value})}/></label>)}
     <button disabled={working}>{working?'Loading...':'Calculate descriptive changes'}</button>
    </form>
    {trend&&<><table><thead><tr><th>Year</th><th>Value</th><th>Unit</th><th>Dataset</th></tr></thead><tbody>{trend.series.map((r,i)=><tr key={i}><td>{r.year}</td><td>{r.value}</td><td>{r.unit}</td><td><a href={r.source_url} rel="noreferrer" target="_blank">{r.dataset_name}</a></td></tr>)}</tbody></table>
     <h4>Observed changes</h4>{trend.changes.map((c,i)=><p key={i}>{c.from_year}–{c.to_year}: {c.absolute_change.toLocaleString()} {c.unit} ({c.percentage_change===null?'percentage undefined':c.percentage_change+'%'})</p>}
     <p className="hub-caution">{trend.warning}</p></>}
   </section>
   <section className="hub-panel">
    <h3>Explicit provenance graph</h3>
    {graph?<><p>{graph.nodes.length} nodes · {graph.edges.length} recorded relationships</p>
     <p className="hub-caution">{graph.provenance_policy}</p>
     <div className="advanced-relations"><table><thead><tr><th>Relationship</th><th>From</th><th>To</th></tr></thead><tbody>
       {graph.edges.slice(0,100).map((r,i)=><tr key={i}><td>{r.relation.replaceAll('_',' ')}</td><td>{r.source}</td><td>{r.target}</td></tr>)}
      </tbody></table></div><small>First 100 links shown. Research notes are restricted to projects you can access.</small>
     </>:<p>Loading explicit evidence relationships...</p>}
   </section>
  </div>
 </div>
}
