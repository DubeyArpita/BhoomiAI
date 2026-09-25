export const API='/api';
export function currentToken(){return sessionStorage.getItem('bhoomiai_token')||'';}
export function clearToken(){sessionStorage.removeItem('bhoomiai_token');}
export async function apiFetch(path,options={}){
 const headers=new Headers(options.headers||{});
 const token=currentToken();
 if(token)headers.set('Authorization','Bearer '+token);
 const response=await fetch(path,{...options,headers});
 if(response.status===401 && !path.endsWith('/auth/login')){
  window.dispatchEvent(new Event('bhoomiai-session-expired'));
 }
 return response;
}
