export const API_BASE = '/api';

export async function fetchJson(endpoint) {
    try {
        const res = await fetch(`${API_BASE}${endpoint}`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`API Error on ${endpoint}:`, e);
        throw e;
    }
}
