import React,{useEffect,useMemo,useState} from 'react';
import {API,apiFetch} from './api.js';

const SELECTED = {
 clr:['ror_computerized_pct','villages_clr_completed_pct','ror_linked_cadastral_pct'],
 maps:['digitized_cadastral_maps_pct','georeferenced_map_documents_pct','georeferenced_land_parcels_pct','ulpin_land_parcels_pct'],
 mrr:['mrr_sanctioned_pct','mrr_completed_pct'],
 survey:[],
};

async function getJSON(endpoint){
 const response = await apiFetch(API+endpoint);
 const payload = await response.json().catch(()=>({}));
 if(!response.ok)throw Error(payload.detail||'Official district report unavailable');
 return payload;
}
function fmt(value,unit){
 if(value===null||value===undefined)return 'Not reported';
 if(typeof value==='string')return value;
 return value.toLocaleString(undefined,{maximumFractionDigits:2})+(unit==='%'?'%':unit==='count'?'':' '+unit);
}
function Summary({report}){
 const preferred=SELECTED[report.key]||[];
 const fields=report.fields.filter(f=>preferred.includes(f.key)&&typeof f.value==='number');
 return <div className="dilrmp-mini-cards">
  {fields.map(field=><div key={field.key} className="dilrmp-mini">
    <small>{field.label}</small><strong>{fmt(field.value,field.unit)}</strong>
    {field.unit==='%'&&<div className="dilrmp-bar"><span style={{width:Math.min(100,Math.max(0,field.value))+'%'}}/></div>}
    <span className="dilrmp-cite">Source cell {report.sheet}!{field.cell}</span>
  </div>)}
 </div>;
}
function Report({report,other}){
 const [expanded,setExpanded]=useState(false);
 const comparisons=useMemo(()=>other?.reports?.find(r=>r.key===report.key),[other,report.key]);
 return <section className="dilrmp-report">
  <div className="dilrmp-report-head">
   <h3>{report.title}</h3>
   <a href={report.source_url} target="_blank" rel="noreferrer">Official source ↗</a>
  </div>
  <Summary report={report}/>
  {comparisons&&<p className="small-muted">Comparison: {other.district}. These are simultaneous source snapshots, not trends.</p>}
  <button className="dilrmp-outline" type="button" onClick={()=>setExpanded(x=>!x)}>
   {expanded?'Hide':'Show'} all {report.fields.length} source fields
  </button>
  {expanded&&<div className="dilrmp-table-scroll"><table><thead><tr>
   <th>Indicator</th><th>{report.row?'Selected district':'Value'}</th>
   {comparisons&&<th>{other.district}</th>}<th>Original cell</th>
  </tr></thead><tbody>
   {report.fields.map(field=>{
    const compared=comparisons?.fields.find(f=>f.key===field.key);
    return <tr key={field.key}>
     <td>{field.label}</td><td>{fmt(field.value,field.unit)}</td>
     {comparisons&&<td>{compared?fmt(compared.value,compared.unit):'Not available'}</td>}
     <td><code>{report.sheet}!{field.cell}</code></td>
    </tr>;
   })}
  </tbody></table></div>}
  <div className="dilrmp-foot">Original workbook: <code>{report.source_path}</code> · Sheet: {report.sheet}, row {report.row}. All values are from the named district row.</div>
 </section>;
}
function exportSnapshot(snapshot){
 const rows=[['state','district','report','metric_key','metric','value','unit','workbook','sheet','cell','source_url']];
 for(const report of snapshot.reports){
  for(const f of report.fields)rows.push([snapshot.state,snapshot.district,report.title,
   f.key,f.label,f.value??'',f.unit,report.source_file,report.sheet,f.cell,report.source_url]);
 }
 const quote=value=>'"'+String(value??'').replaceAll('"','""')+'"';
 const csv='\ufeff'+rows.map(r=>r.map(quote).join(',')).join('\r\n');
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download='DILRMP_'+snapshot.district.replaceAll(' ','_')+'_source_snapshot.csv';
 document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
}
export default function DilrmpPage(){
 const [districts,setDistricts]=useState([]),[district,setDistrict]=useState('GHAZIABAD');
 const [comparison,setComparison]=useState(''),[snapshot,setSnapshot]=useState(null),[other,setOther]=useState(null);
 const [loading,setLoading]=useState(true),[error,setError]=useState('');
 useEffect(()=>{
  getJSON('/dilrmp/districts').then(payload=>setDistricts(payload.districts))
   .catch(e=>setError(e.message));
 },[]);
 useEffect(()=>{
  let active=true;setLoading(true);setError('');
  Promise.all([getJSON('/dilrmp/district?district='+encodeURIComponent(district)),
   comparison?getJSON('/dilrmp/district?district='+encodeURIComponent(comparison)):Promise.resolve(null)])
   .then(([first,second])=>{if(active){setSnapshot(first);setOther(second)}})
   .catch(e=>{if(active)setError(e.message)})
   .finally(()=>{if(active)setLoading(false)});
  return ()=>{active=false};
 },[district,comparison]);
 return <div className="dilrmp-page">
  <header className="dilrmp-header"><div className="eyebrow">OFFICIAL EVIDENCE · UTTAR PRADESH</div>
   <h2>DILRMP district dashboard</h2>
   <p>Published land-record modernization indicators, read directly from the four original Excel workbooks committed to BhoomiAI.</p>
  </header>
  <div className="dilrmp-content">
   <div className="dilrmp-filters">
    <label>District
     <select value={district} onChange={e=>setDistrict(e.target.value)}>
      {districts.length?districts.map(name=><option key={name} value={name}>{name}</option>):<option>GHAZIABAD</option>}
     </select>
    </label>
    <label>Compare with (optional)
     <select value={comparison} onChange={e=>setComparison(e.target.value)}>
      <option value="">No comparison</option>
      {districts.filter(name=>name!==district).map(name=><option key={name} value={name}>{name}</option>)}
     </select>
    </label>
    <button type="button" disabled={!snapshot||loading} onClick={()=>exportSnapshot(snapshot)}>Export sourced CSV</button>
   </div>
   {error&&<p className="hub-message" role="alert">{error}</p>}
   {loading?<p className="small-muted">Reading the committed official Excel reports...</p>:snapshot&&<>
    <div className="dilrmp-disclaimer">
     <strong>{snapshot.district}, {snapshot.state}</strong>
     <p>These files contain records for all Uttar Pradesh districts. This page selects the actual {snapshot.district} row from each workbook, rather than treating the state totals as district data.</p>
     <p><strong>Reporting date unavailable:</strong> this is a single downloaded snapshot. The chart bars show reported completion percentages, not historical change or verified programme outcomes.</p>
    </div>
    {snapshot.reports.map(report=><Report key={report.key} report={report} other={other}/>)}
    {snapshot.missing_reports.length>0&&<div className="dilrmp-disclaimer">Missing or changed source layout: {snapshot.missing_reports.join(' · ')}</div>}
    <p className="small-muted">Percentage denominators follow the headings in each original sheet. Blank cells are shown as not reported. Source URLs point to the official downloads page; original worksheet and cell coordinates accompany every figure.</p>
   </>}
  </div>
 </div>;
}