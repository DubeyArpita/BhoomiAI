import React,{useEffect,useState} from 'react';
import {MapContainer,TileLayer,GeoJSON,ScaleControl,LayersControl} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
const API='/api';
const INITIAL_CENTER=[28.669,77.453];
const MAX_VISIBLE_FEATURES=1000;
function MapLayers({data,visible}){
 return data.filter(layer=>visible.includes(layer.id)).map(layer=>
   <GeoJSON key={layer.id} data={layer.data} style={()=>({color:'#227b58',weight:2,fillOpacity:0.25})}
     pointToLayer={(feature,latlng)=>L.circleMarker(latlng,{radius:6,color:'#227b58',fillOpacity:.65})}
     onEachFeature={(feature,polygon)=>{
       const attrs=Object.entries(feature.properties||{}).slice(0,12);
       const text=attrs.map(([k,v])=>k+': '+String(v).slice(0,100)).join('\n');
       polygon.bindPopup(L.popup().setContent(
         L.DomUtil.create('pre','gis-popup')
       ));
       const popup=polygon.getPopup(); if(popup)popup.getContent().textContent=text||'No attributes';
     }}/>);
}
export default function GISPage(){
 const [layers,setLayers]=useState([]),[loaded,setLoaded]=useState([]),[visible,setVisible]=useState([]),[showTiles,setShowTiles]=useState(false);
 const [name,setName]=useState(''),[source,setSource]=useState(''),[licence,setLicence]=useState(''),[description,setDescription]=useState('');
 const [file,setFile]=useState(null),[loading,setLoading]=useState(false),[message,setMessage]=useState('');
 async function list(){
  const r=await fetch(API+'/gis/layers');if(!r.ok)throw Error('GIS backend unavailable');
  setLayers(await r.json());
 }
 useEffect(()=>{list().catch(e=>setMessage(e.message))},[]);
 async function toggle(layer){
  if(visible.includes(layer.id)){setVisible(p=>p.filter(id=>id!==layer.id));return}
  if(!loaded.some(item=>item.id===layer.id)){
   try{
    setMessage('Loading '+layer.name+'...');
    const r=await fetch(API+'/gis/layers/'+layer.id+'/features?limit='+MAX_VISIBLE_FEATURES);
    if(!r.ok)throw Error('Could not fetch map features');
    const data=await r.json();
    setLoaded(p=>[...p,{id:layer.id,data}]);
    if(data.truncated)setMessage('Showing the first '+MAX_VISIBLE_FEATURES+' features. Apply smaller layers for detailed mapping.');
    else setMessage('');
   }catch(e){setMessage(e.message);return}
  }
  setVisible(p=>[...p,layer.id]);
 }
 async function submit(event){
  event.preventDefault();if(!file||!name.trim())return;
  setLoading(true);setMessage('Importing geospatial layer...');
  const body=new FormData();
  body.append('file',file);body.append('name',name);body.append('source_url',source);
  body.append('licence',licence);body.append('description',description);
  try{
   const r=await fetch(API+'/gis/layers',{method:'POST',body});
   const result=await r.json();
   if(!r.ok)throw Error(result.detail||'Import failed');
   setMessage('Imported '+result.features+' features into '+result.name);
   setName('');setFile(null);setSource('');setLicence('');setDescription('');
   document.getElementById('geo-file').value='';
   await list();
  }catch(e){setMessage(e.message)}finally{setLoading(false)}
 }
 async function remove(layer){
  if(!window.confirm('Delete GIS layer '+layer.name+'?'))return;
  try{
   const r=await fetch(API+'/gis/layers/'+layer.id,{method:'DELETE'});
   if(!r.ok)throw Error('Could not delete layer');
   setLoaded(p=>p.filter(x=>x.id!==layer.id));setVisible(p=>p.filter(id=>id!==layer.id));await list();
   setMessage('Layer deleted.');
  }catch(e){setMessage(e.message)}
 }
 return <div className="gis-section">
  <header className="gis-header"><div className="eyebrow">STAGE 2 · GEOSPATIAL DATA</div><h2>GIS Explorer</h2><p>Upload permitted GeoJSON layers, inspect their attributes and overlay them on an interactive map.</p></header>
  <div className="gis-layout">
   <aside className="gis-panel">
    <h3>Import a GIS layer</h3>
    <form onSubmit={submit} className="gis-upload">
     <label>Layer name<input required maxLength={140} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Sample land-cover polygons"/></label>
     <label>GeoJSON (EPSG:4326)<input id="geo-file" required type="file" accept=".geojson,.json,application/geo+json" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
     <label>Source URL<input type="url" value={source} onChange={e=>setSource(e.target.value)} placeholder="https://official-source.example"/></label>
     <label>Dataset licence<input value={licence} onChange={e=>setLicence(e.target.value)} placeholder="e.g. CC BY 4.0"/></label>
     <label>Description<textarea value={description} onChange={e=>setDescription(e.target.value)} placeholder="Data origin, acquisition date and limitations" rows={3}/></label>
     <button type="submit" disabled={loading}>{loading?'Importing...':'Import layer'}</button>
    </form>
    {message&&<p className="gis-notice" role="status">{message}</p>}
    <h3>Available layers ({layers.length})</h3>
    {!layers.length&&<p className="small-muted">No layers imported yet. Try the clearly labelled synthetic sample in sample_data/.</p>}
    {layers.map(layer=><div className="gis-layer" key={layer.id}>
     <label><input type="checkbox" checked={visible.includes(layer.id)} onChange={()=>toggle(layer)}/><strong>{layer.name}</strong></label>
     <small>{layer.feature_count} features {layer.licence&&'· '+layer.licence}</small>
     {layer.source_url&&<a href={layer.source_url} target="_blank" rel="noreferrer">View dataset source</a>}
     <button type="button" className="gis-delete" onClick={()=>remove(layer)}>Delete layer</button>
    </div>)}
   </aside>
   <div className="gis-map-area">
    <div className="map-toolbar"><label><input type="checkbox" checked={showTiles} onChange={e=>setShowTiles(e.target.checked)}/> Online OpenStreetMap basemap (optional)</label><small>Basemap requires internet; uploaded features remain locally stored.</small></div>
    <MapContainer center={INITIAL_CENTER} zoom={10} scrollWheelZoom={true} className="gis-map">
     {showTiles&&<TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>}
     <ScaleControl position="bottomleft"/>
     <MapLayers data={loaded} visible={visible}/>
    </MapContainer>
    <p className="small-muted">View is initially centred near Ghaziabad for demonstration only. Layers use their original imported geographic coordinates; sample polygons are synthetic, not official boundaries.</p>
   </div>
  </div>
 </div>
}
