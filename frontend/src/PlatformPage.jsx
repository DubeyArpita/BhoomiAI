import React,{useEffect,useState} from 'react';
import {LineChart,Line,XAxis,YAxis,CartesianGrid,Tooltip,ResponsiveContainer,Legend} from 'recharts';
import {API,apiFetch} from './api.js';
const tabs=['Overview','Research Workspaces','Policy Lab','Innovation Portal','Satellite Lab','Evidence Graph'];
async function request(path,options){
 const response=await apiFetch(API+path,options);
 const ct=response.headers.get('content-type')||'';
 const data=ct.includes('application/json')?await response.json():await response.text();
 if(!response.ok)throw Error(typeof data==='object'?data.detail||'Request failed':data);
 return data;
}
const emptyProject={title:'',description:'',region:''};
const emptyIndicator={state:'',district:'',year:2025,indicator:'',value:'',unit:'',dataset_name:'',source_url:''};
function Panel({title,children}){return <section className="hub-panel"><h3>{title}</h3>{children}</section>}
function Message({text}){return text?<p className="hub-message" role="status">{text}</p>:null}
export default function PlatformPage({user}){
 const [tab,setTab]=useState('Overview'),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const [projects,setProjects]=useState([]),[chosen,setChosen]=useState(''),[notes,setNotes]=useState([]);
 const [projectForm,setProjectForm]=useState(emptyProject),[note,setNote]=useState({body:'',source_url:'',document_id:''});
 const [users,setUsers]=useState([]),[invite,setInvite]=useState({name:'',email:'',password:'',role:'researcher'});
 const [indicators,setIndicators]=useState([]),[indicatorForm,setIndicatorForm]=useState(emptyIndicator),[insights,setInsights]=useState(null);
 const [scenario,setScenario]=useState({total_area_ha:10000,baseline_conversion_ha:800,proposed_restriction_fraction:0.25,assumed_compliance_fraction:0.7});
 const [scenarioResult,setScenarioResult]=useState(null),[challenges,setChallenges]=useState([]);
 const [challenge,setChallenge]=useState({title:'',description:'',deadline:''}),[submission,setSubmission]=useState({title:'',abstract:''});
 const [selectedChallenge,setSelectedChallenge]=useState(''),[graph,setGraph]=useState({nodes:[],edges:[]}),[docs,setDocs]=useState([]);
 const [chosenDoc,setChosenDoc]=useState(''),[recommendations,setRecommendations]=useState([]);
 const [rasters,setRasters]=useState([]),[rasterFile,setRasterFile]=useState(null);
 const [rasterForm,setRasterForm]=useState({title:'',capture_date:'',platform:'Sentinel-2',source_url:'',licence:''});
 const [comparison,setComparison]=useState({before_id:'',after_id:'',red_band:1,nir_band:2,ndvi_drop_threshold:0.2});
 const [changeResult,setChangeResult]=useState(null),[previewSrc,setPreviewSrc]=useState('');
 const admin=user?.role==='admin',editable=user?.role!=='viewer';
 async function load(){
  setLoading(true);
  const endpoints=[
   ['/platform/projects',setProjects],['/platform/indicators',setIndicators],
   ['/platform/insights',setInsights],['/platform/challenges',setChallenges],
   ['/platform/graph',setGraph],['/documents',setDocs],['/raster/scenes',setRasters]
  ];
  const outcomes=await Promise.allSettled(endpoints.map(async([path,update])=>update(await request(path))));
  const errors=outcomes.filter(x=>x.status==='rejected');
  if(errors.length)setError('Some panels could not load: '+errors.map(e=>e.reason.message).join('; '));
  if(admin){try{setUsers(await request('/platform/users'))}catch(e){setError(e.message)}}
  setLoading(false);
 }
 useEffect(()=>{load()},[]);
 useEffect(()=>{if(chosen)request('/platform/projects/'+chosen+'/notes').then(setNotes).catch(e=>setError(e.message));else setNotes([])},[chosen]);
 function action(run){return async e=>{e?.preventDefault?.();setError('');try{await run();await load()}catch(ex){setError(ex.message)}}}
 async function exportReport(){
  try{
   const r=await apiFetch(API+'/platform/projects/'+chosen+'/report');
   if(!r.ok)throw Error('Could not export report');
   const blob=await r.blob(),url=URL.createObjectURL(blob);
   const a=document.createElement('a');a.href=url;a.download='bhoomiai-project-'+chosen+'.md';
   a.click();URL.revokeObjectURL(url);
  }catch(e){setError(e.message)}
 }
 async function preview(scene){
  try{
   if(previewSrc)URL.revokeObjectURL(previewSrc);
   const r=await apiFetch(API+'/raster/scenes/'+scene.id+'/preview');
   if(!r.ok)throw Error('Unable to create preview');
   setPreviewSrc(URL.createObjectURL(await r.blob()));
  }catch(e){setError(e.message)}
 }
 function format(value){return Number.isFinite(Number(value))?Number(value).toLocaleString(undefined,{maximumFractionDigits:3}):String(value)}
 const selection=projects.find(p=>String(p.id)===String(chosen));
 const series=[...new Set(indicators.map(i=>i.indicator))];
 const graphNodes=graph.nodes?.slice(0,24)||[];
 const byId=Object.fromEntries(graphNodes.map((n,i)=>[n.id,{...n,x:210+155*Math.cos(i*2*Math.PI/Math.max(1,graphNodes.length)),y:190+155*Math.sin(i*2*Math.PI/Math.max(1,graphNodes.length))}]));
 return <div className="hub"><header className="hub-header"><div className="eyebrow">STAGES 3–5 · INTEGRATED PROTOTYPE</div><h2>Research & Policy Hub</h2><p>Collaborative projects, sourced indicators, transparent scenarios and evidence discovery.</p></header>
  <div className="hub-tabs">{tabs.map(t=><button type="button" key={t} className={tab===t?'selected':''} onClick={()=>setTab(t)}>{t}</button>)}</div>
  <Message text={error}/>{loading&&<p>Loading platform data...</p>}
  {tab==='Overview'&&<div className="hub-grid">
   <Panel title="Current local repository"><div className="hub-metrics"><div><strong>{insights?.total_indexed_documents??'—'}</strong><small>Indexed documents</small></div><div><strong>{projects.length}</strong><small>Visible projects</small></div><div><strong>{indicators.length}</strong><small>Sourced indicator records</small></div><div><strong>{rasters.length}</strong><small>Local raster scenes</small></div></div><p className="hub-caution">Numbers describe this local database only. They do not represent national land statistics.</p></Panel>
   <Panel title="Dataset and research coverage">{!insights?.by_region?.length?<p>No indexed research documents yet.</p>:<table><thead><tr><th>State</th><th>District</th><th>Indexed documents</th></tr></thead><tbody>{insights.by_region.map((r,i)=><tr key={i}><td>{r.state}</td><td>{r.district}</td><td>{r.count}</td></tr>)}</tbody></table>}<p className="hub-caution">Missing indexed publications may indicate collection gaps, not an absence of published research.</p></Panel>
   <Panel title="Indicators dashboard">
    <p>All entries require an identifiable source and are entered by an administrator.</p>
    {series.map(label=>{const records=indicators.filter(i=>i.indicator===label);
     return <div className="chart-wrapper" key={label}><h4>{label} ({records[0]?.unit})</h4><ResponsiveContainer width="100%" height={230}><LineChart data={records.map(i=>({year:i.year,value:i.value,location:i.district+' / '+i.state})).sort((a,b)=>a.year-b.year)}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="year"/><YAxis/><Tooltip/><Legend/><Line type="linear" dataKey="value" name={label} stroke="#36775c" strokeWidth={2}/></LineChart></ResponsiveContainer><small>Multiple locations may appear in this exploratory chart. Filter by location when making comparisons.</small></div>})}
    {!series.length&&<p>No sourced indicators yet. Add them in the Policy Lab.</p>}
   </Panel>
  </div>}
  {tab==='Research Workspaces'&&<div className="hub-grid">
   <Panel title="Create a research project">{editable&&<form onSubmit={action(async()=>{await request('/platform/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(projectForm)});setProjectForm(emptyProject)})}>
    <input required placeholder="Project title" value={projectForm.title} onChange={e=>setProjectForm({...projectForm,title:e.target.value})}/>
    <input placeholder="Region" value={projectForm.region} onChange={e=>setProjectForm({...projectForm,region:e.target.value})}/>
    <textarea required rows={3} placeholder="Research objective" value={projectForm.description} onChange={e=>setProjectForm({...projectForm,description:e.target.value})}/>
    <button>Create project</button></form>}
    <h4>Your accessible projects</h4><select value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">Choose a project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.title} — {p.region||'Unspecified'}</option>)}</select>
   </Panel>
   {selection&&<Panel title={'Evidence notebook: '+selection.title}>
    {editable&&<form onSubmit={action(async()=>{await request('/platform/projects/'+chosen+'/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...note,document_id:note.document_id?Number(note.document_id):null})});setNote({body:'',source_url:'',document_id:''});setNotes(await request('/platform/projects/'+chosen+'/notes'))})}>
     <textarea required rows={4} placeholder="Observation, methodological note or evidence claim" value={note.body} onChange={e=>setNote({...note,body:e.target.value})}/>
     <input type="url" placeholder="Original evidence URL (if applicable)" value={note.source_url} onChange={e=>setNote({...note,source_url:e.target.value})}/>
     <select value={note.document_id} onChange={e=>setNote({...note,document_id:e.target.value})}><option value="">No linked document</option>{docs.map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</select>
     <button>Save evidence note</button></form>}
    <button type="button" onClick={exportReport}>Export evidence report (.md)</button>
    {notes.map(n=><div className="evidence-note" key={n.id}><span className="hub-tag">{n.review_status}</span><small>{n.author}</small><p>{n.body}</p>{n.source_url&&<a href={n.source_url} target="_blank" rel="noreferrer">Original source</a>}{editable&&n.review_status==='pending'&&n.author!==user.name&&<div><button type="button" onClick={action(async()=>{await request('/platform/notes/'+n.id+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:'confirmed'})});setNotes(await request('/platform/projects/'+chosen+'/notes'))})}>Confirm</button><button type="button" className="secondary" onClick={action(async()=>{await request('/platform/notes/'+n.id+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:'rejected'})});setNotes(await request('/platform/projects/'+chosen+'/notes'))})}>Reject</button></div>}</div>)}
    {!notes.length&&<p>No evidence notes yet.</p>}
   </Panel>}
   {admin&&<Panel title="Team administration"><form onSubmit={action(async()=>{await request('/platform/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(invite)});setInvite({name:'',email:'',password:'',role:'researcher'})})}><input required placeholder="Researcher name" value={invite.name} onChange={e=>setInvite({...invite,name:e.target.value})}/><input type="email" required placeholder="Email" value={invite.email} onChange={e=>setInvite({...invite,email:e.target.value})}/><input type="password" required minLength={12} placeholder="Temporary password (12+ chars)" value={invite.password} onChange={e=>setInvite({...invite,password:e.target.value})}/><select value={invite.role} onChange={e=>setInvite({...invite,role:e.target.value})}><option>researcher</option><option>official</option><option>viewer</option></select><button>Create account</button></form><small>Share initial credentials privately; password-reset workflow remains to be built.</small>{users.map(u=><p key={u.id}>{u.id} · {u.name} · {u.role}</p>)}{selection&&<form onSubmit={action(async(e)=>{const field=e.target.elements.memberId;await request('/platform/projects/'+chosen+'/members',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:Number(field.value)})})})}><label>Add a member to selected project<select name="memberId" required><option value="">Select team member</option>{users.map(u=><option key={u.id} value={u.id}>{u.name}</option>)}</select></label><button>Add member</button></form>}</Panel>}
  </div>}
  {tab==='Policy Lab'&&<div className="hub-grid">
   <Panel title="Hypothetical land-conversion scenario"><p>Enter assumed quantities. Calculations do not predict actual effects.</p><form onSubmit={async e=>{e.preventDefault();try{setScenarioResult(await request('/platform/scenarios',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(Object.entries(scenario).map(([k,v])=>[k,Number(v)])))}))}catch(ex){setError(ex.message)}}}>
    {Object.entries(scenario).map(([key,value])=><label key={key}>{key.replaceAll('_',' ')}<input type="number" required step="any" min="0" max={key.includes('fraction')?1:undefined} value={value} onChange={e=>setScenario({...scenario,[key]:e.target.value})}/></label>)}
    <button>Calculate scenario</button></form>
    {scenarioResult&&<div className="scenario-result"><strong>Hypothetical avoided conversion: {format(scenarioResult.hypothetical_avoided_conversion_ha)} ha</strong><p>Hypothetical conversion: {format(scenarioResult.hypothetical_conversion_ha)} ha</p><small>{scenarioResult.formula}</small><p className="hub-caution">{scenarioResult.warning}</p><p>{scenarioResult.assumptions}</p></div>}
   </Panel>
   <Panel title="Sourced monitoring indicators">
    {admin&&<form onSubmit={action(async()=>{await request('/platform/indicators',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...indicatorForm,year:Number(indicatorForm.year),value:Number(indicatorForm.value)})});setIndicatorForm(emptyIndicator)})}>
     {Object.entries(indicatorForm).map(([field,value])=><label key={field}>{field.replaceAll('_',' ')}<input required type={field==='year'||field==='value'?'number':field==='source_url'?'url':'text'} step={field==='value'?'any':undefined} value={value} onChange={e=>setIndicatorForm({...indicatorForm,[field]:e.target.value})}/></label>)}
     <button>Add sourced indicator</button></form>}
    <table><thead><tr><th>Location</th><th>Year</th><th>Indicator</th><th>Value</th><th>Source</th></tr></thead><tbody>{indicators.map(i=><tr key={i.id}><td>{i.district}, {i.state}</td><td>{i.year}</td><td>{i.indicator}</td><td>{format(i.value)} {i.unit}</td><td><a target="_blank" rel="noreferrer" href={i.source_url}>{i.dataset_name}</a></td></tr>)}</tbody></table>
   </Panel>
  </div>}
  {tab==='Innovation Portal'&&<div className="hub-grid">
   {admin&&<Panel title="Publish a research challenge"><form onSubmit={action(async()=>{await request('/platform/challenges',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...challenge,deadline:challenge.deadline||null})});setChallenge({title:'',description:'',deadline:''})})}><input required placeholder="Challenge title" value={challenge.title} onChange={e=>setChallenge({...challenge,title:e.target.value})}/><textarea required rows={3} placeholder="Research problem and submission requirements" value={challenge.description} onChange={e=>setChallenge({...challenge,description:e.target.value})}/><input type="date" value={challenge.deadline} onChange={e=>setChallenge({...challenge,deadline:e.target.value})}/><button>Publish challenge</button></form></Panel>}
   <Panel title="Research competitions and pilots">{challenges.map(c=><div className="evidence-note" key={c.id}><strong>{c.title}</strong><p>{c.description}</p><small>Deadline: {c.deadline||'Unspecified'}</small><button type="button" onClick={()=>setSelectedChallenge(String(c.id))}>Submit proposal</button></div>)}{!challenges.length&&<p>No challenges have been published yet.</p>}{selectedChallenge&&editable&&<form onSubmit={action(async()=>{await request('/platform/challenges/'+selectedChallenge+'/submissions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(submission)});setSubmission({title:'',abstract:''});setSelectedChallenge('')})}><h4>Submit your research proposal</h4><input required placeholder="Proposal title" value={submission.title} onChange={e=>setSubmission({...submission,title:e.target.value})}/><textarea required rows={4} placeholder="Abstract" value={submission.abstract} onChange={e=>setSubmission({...submission,abstract:e.target.value})}/><button>Submit proposal</button></form>}</Panel>
  </div>}
  {tab==='Satellite Lab'&&<div className="hub-grid">
   <Panel title="Import a local, licensed GeoTIFF">{editable&&<form onSubmit={action(async()=>{if(!rasterFile)throw Error('Choose a TIFF first');const body=new FormData();body.append('file',rasterFile);Object.entries(rasterForm).forEach(([k,v])=>body.append(k,v));await request('/raster/scenes',{method:'POST',body});setRasterForm({title:'',capture_date:'',platform:'Sentinel-2',source_url:'',licence:''});setRasterFile(null)})}><input required type="file" accept=".tif,.tiff" onChange={e=>setRasterFile(e.target.files?.[0]||null)}/>{Object.entries(rasterForm).map(([k,v])=><label key={k}>{k.replaceAll('_',' ')}<input required type={k==='capture_date'?'date':k==='source_url'?'url':'text'} value={v} onChange={e=>setRasterForm({...rasterForm,[k]:e.target.value})}/></label>)}<button>Import scene</button></form>}
    {rasters.map(s=><div className="evidence-note" key={s.id}><strong>{s.title}</strong><p>{s.platform} · {s.capture_date} · {s.bands} bands</p><a href={s.source_url} target="_blank" rel="noreferrer">Original source</a><button type="button" onClick={()=>preview(s)}>Generate preview</button></div>)}
    {previewSrc&&<img className="raster-preview" src={previewSrc} alt="Display-only raster preview; band-to-RGB mapping may not reflect true colour"/>}
   </Panel>
   <Panel title="Exploratory vegetation-index comparison"><p>Use two overlapping reflectance rasters from compatible dates and choose the correct red and near-infrared band positions for each file.</p><form onSubmit={async e=>{e.preventDefault();try{setChangeResult(await request('/raster/compare-vegetation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...comparison,red_band:Number(comparison.red_band),nir_band:Number(comparison.nir_band),ndvi_drop_threshold:Number(comparison.ndvi_drop_threshold)})}))}catch(ex){setError(ex.message)}}}><label>Earlier scene<select required value={comparison.before_id} onChange={e=>setComparison({...comparison,before_id:e.target.value})}><option value="">Choose image</option>{rasters.map(s=><option key={s.id} value={s.id}>{s.title} · {s.capture_date}</option>)}</select></label><label>Later scene<select required value={comparison.after_id} onChange={e=>setComparison({...comparison,after_id:e.target.value})}><option value="">Choose image</option>{rasters.map(s=><option key={s.id} value={s.id}>{s.title} · {s.capture_date}</option>)}</select></label>{['red_band','nir_band','ndvi_drop_threshold'].map(k=><label key={k}>{k.replaceAll('_',' ')}<input required type="number" min={k==='ndvi_drop_threshold'?0.01:1} max={k==='ndvi_drop_threshold'?1:20} step={k==='ndvi_drop_threshold'?.01:1} value={comparison[k]} onChange={e=>setComparison({...comparison,[k]:e.target.value})}/></label>)}<button>Compare vegetation indices</button></form>{changeResult&&<div className="scenario-result"><strong>Mean NDVI difference: {format(changeResult.mean_ndvi_delta)}</strong><p>Fraction with NDVI drop: {format(changeResult.fraction_with_ndvi_drop*100)}%</p><p className="hub-caution">{changeResult.limitations}</p></div>}</Panel>
  </div>}
  {tab==='Evidence Graph'&&<div className="hub-grid">
   <Panel title="Evidence-linked knowledge graph"><p>{graph.nodes?.length||0} indexed nodes and {graph.edges?.length||0} explicit links (first 24 nodes visualized).</p><svg viewBox="0 0 420 380" className="evidence-graph" role="img" aria-label="Research evidence graph">{(graph.edges||[]).filter(e=>byId[e.source]&&byId[e.target]).map((e,i)=><line key={i} x1={byId[e.source].x} y1={byId[e.source].y} x2={byId[e.target].x} y2={byId[e.target].y} stroke="#a9c4ae" strokeWidth="1.4"/>)}{graphNodes.map(n=><g key={n.id}><circle cx={byId[n.id].x} cy={byId[n.id].y} r="9" fill={n.type==='document'?'#498b6d':n.type==='project'?'#5682b7':'#c1a35f'}/><text x={byId[n.id].x+11} y={byId[n.id].y+3} fontSize="8.5" fill="currentColor">{n.label.slice(0,20)}</text></g>)}</svg><small>{graph.note}</small></Panel>
   <Panel title="Research coverage and discovery"><p>Identify regions that have limited coverage in <strong>our indexed documents</strong>, not in the entire research literature.</p>{insights?.by_region?.map((r,i)=><p key={i}>{r.state} / {r.district}: <strong>{r.count} indexed documents</strong></p>)}
    <h4>Find similar indexed publications</h4><select value={chosenDoc} onChange={e=>setChosenDoc(e.target.value)}><option value="">Select document</option>{docs.map(d=><option value={d.id} key={d.id}>{d.title||d.filename}</option>)}</select><button type="button" disabled={!chosenDoc} onClick={async()=>{try{setRecommendations(await request('/platform/recommendations/'+chosenDoc))}catch(e){setError(e.message)}}}>Discover related documents</button>{recommendations.map(r=><p key={r.document_id}>{r.title} · similarity {format(r.similarity)} {r.source_url&&<a href={r.source_url} target="_blank" rel="noreferrer">Source</a>}</p>)}
   </Panel>
  </div>}
 </div>;
}
