import axios from 'axios';
export const api = axios.create({baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000', timeout: 15000});
export function errorMessage(error) {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map(item => `${item.loc.slice(1).join('.')}: ${item.msg}`).join('; ');
  return typeof detail === 'string' ? detail : 'Cannot reach the server. Check that the backend and database are running.';
}
export async function listAll(path) {
  const rows = [];
  for (let offset = 0; ; offset += 200) {
    const {data} = await api.get(path, {params: {offset, limit: 200}});
    rows.push(...data);
    if (data.length < 200) return rows;
  }
}
