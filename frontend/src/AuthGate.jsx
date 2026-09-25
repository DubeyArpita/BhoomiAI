import React,{useEffect,useState} from 'react';
import {API,apiFetch,currentToken,clearToken} from './api.js';
export default function AuthGate({children}){
 const [user,setUser]=useState(null),[checking,setChecking]=useState(true);
 const [register,setRegister]=useState(false),[name,setName]=useState('');
 const [email,setEmail]=useState(''),[password,setPassword]=useState('');
 const [setupKey,setSetupKey]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{
  let active=true;
  async function check(){
   try{const r=await apiFetch(API+'/platform/auth/me');if(!r.ok)throw Error('Sign in');const u=await r.json();if(active)setUser(u)}
   catch{if(active)setUser(null)}
   finally{if(active)setChecking(false)}
  }
  if(currentToken())check();else setChecking(false);
  const expired=()=>{clearToken();setUser(null)};
  window.addEventListener('bhoomiai-session-expired',expired);
  return()=>{active=false;window.removeEventListener('bhoomiai-session-expired',expired)};
 },[]);
 async function submit(e){
  e.preventDefault();setMessage('');setBusy(true);
  try{
   if(register){
    const response=await fetch(API+'/platform/auth/bootstrap',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({name,email,password,setup_key:setupKey})});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Setup failed');
   }
   const response=await fetch(API+'/platform/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({email,password})});
   const data=await response.json();if(!response.ok)throw Error(data.detail||'Sign-in failed');
   sessionStorage.setItem('bhoomiai_token',data.access_token);setUser(data.user);
  }catch(error){setMessage(error.message)}
  finally{setBusy(false)}
 }
 if(checking)return <main className="auth-screen">Restoring your session...</main>;
 if(user)return <><div className="account-bar"><span>Signed in: {user.name} ({user.role})</span><button type="button" onClick={()=>{clearToken();setUser(null)}}>Sign out</button></div>{React.cloneElement(children,{user})}</>;
 return <div className="auth-screen"><form className="auth-form" onSubmit={submit}>
  <h1>🌿 BhoomiAI</h1><p>Research and land-governance workspace</p>
  <h2>{register?'Create initial administrator':'Sign in'}</h2>
  {register&&<label>Your name<input required value={name} onChange={e=>setName(e.target.value)}/></label>}
  <label>Email<input type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label>
  <label>Password (12+ characters)<input type="password" required minLength={12} value={password} onChange={e=>setPassword(e.target.value)}/></label>
  {register&&<label>One-time setup key<input type="password" required value={setupKey} onChange={e=>setSetupKey(e.target.value)}/></label>}
  <button disabled={busy}>{busy?'Please wait...':register?'Create admin and sign in':'Sign in'}</button>
  {message&&<p role="alert" className="auth-error">{message}</p>}
  <button type="button" className="auth-switch" onClick={()=>{setRegister(!register);setMessage('')}}>{register?'Back to sign in':'First-time setup: create administrator'}</button>
  <small>For new installations, generate SESSION_SECRET and BOOTSTRAP_KEY in backend/.env first.</small>
 </form></div>
}
