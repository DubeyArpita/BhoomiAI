// Local development uses the Vite /api proxy. Hosted builds point directly to the Render API.
export const API=import.meta.env.VITE_API_BASE || '/api';
export async function apiFetch(path,options={}){
 return fetch(path,options);
}
