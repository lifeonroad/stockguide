import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export async function runScreen(strategyId) {
    const tbody = document.getElementById('screener-table-body');
    const title = document.getElementById('screener-results-title');

    tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-8 text-center text-warren-accent animate-pulse">Running Strategy Scan... (This may take 10s)</td></tr>';

    const names = {
        'magic_formula': 'Magic Formula 🪄',
        'rule_of_40': 'Rule of 40 🚀',
        'lynch': 'Peter Lynch Growth 📈',
        'deep_value': 'Deep Value 💎',
        'moat_masters': 'Moat Masters 🏰',
        'quality_compounders': 'Quality Compounders 👑',
        'fallen_angels': 'Fallen Angels 🔥',
        'burry_orphans': 'Burry\'s Orphans 🦉'
    };
    title.textContent = `Results: ${names[strategyId] || 'Custom Scan'}`;

    try {
        const res = await fetch(`${API_BASE}/screeners/${strategyId}`);
        const payload = await res.json();

        const titleBadge = payload.universe_meta ? window.renderUniverseBadge(payload.universe_meta) : '';
        title.innerHTML = `Results: ${names[strategyId] || 'Custom Scan'} ${titleBadge}`;

        const data = Array.isArray(payload) ? payload : (payload.stocks || payload.results || []);

        tbody.innerHTML = '';

        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-8 text-center text-gray-400">No stocks in our universe matched this strict criteria.</td></tr>';
            return;
        }

        data.forEach(stock => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-800/50 transition-colors border-b border-gray-800 last:border-0";
            tr.innerHTML = `
                <td class="px-6 py-4">
                    <div class="font-bold text-white text-lg">${linkTV(stock.symbol)}</div>
                    <div class="text-xs text-gray-500">${stock.name}</div>
                </td>
                <td class="px-6 py-4">
                    <span class="text-sm text-gray-300 font-medium">${stock.reason}</span>
                </td>
                <td class="px-6 py-4 text-right font-mono text-white">
                    $${stock.price}
                </td>
                <td class="px-6 py-4 text-right">
                    <button onclick="window.searchStock('${stock.symbol}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                        Analyze
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Screen failed", err);
        tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-8 text-center text-red-400">Scan failed. Server may be busy.</td></tr>';
    }
}
