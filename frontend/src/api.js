// Local SIH demonstration: requests are proxied to loopback-only FastAPI.
export const API='/api';
export async function apiFetch(path,options={}){
 return fetch(path,options);
}
