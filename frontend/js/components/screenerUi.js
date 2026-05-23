import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

function _inflationBadge(score) {
    if (score >= 80) return { label: 'Inflation Proof', cls: 'bg-green-500/20 text-green-300 border-green-500/30' };
    if (score >= 65) return { label: 'Well Shielded', cls: 'bg-blue-500/20 text-blue-300 border-blue-500/30' };
    if (score >= 50) return { label: 'Adequate', cls: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' };
    return { label: 'Vulnerable', cls: 'bg-red-500/20 text-red-300 border-red-500/30' };
}

export async function runScreen(strategyId) {
    const tbody = document.getElementById('screener-table-body');
    const title = document.getElementById('screener-results-title');

    const names = {
        'magic_formula': 'Magic Formula 🪄',
        'rule_of_40': 'Rule of 40 🚀',
        'lynch': 'Peter Lynch Growth 📈',
        'deep_value': 'Deep Value 💎',
        'moat_masters': 'Moat Masters 🏰',
        'quality_compounders': 'Quality Compounders 👑',
        'fallen_angels': 'Fallen Angels 🔥',
        'burry_orphans': 'Burry\'s Orphans 🦉',
        'inflation_busters': 'Inflation Busters 🛡️'
    };

    // Custom header for inflation_busters
    const isInflation = strategyId === 'inflation_busters';
    if (isInflation) {
        document.querySelector('#screeners-view thead tr').innerHTML = `
            <th class="px-4 py-3 rounded-l-lg">Ticker</th>
            <th class="px-4 py-3 text-center">Score</th>
            <th class="px-4 py-3 text-right">ROE</th>
            <th class="px-4 py-3 text-right">D/E</th>
            <th class="px-4 py-3 text-right">FCF Yield</th>
            <th class="px-4 py-3 text-right">Sector</th>
            <th class="px-4 py-3 text-right rounded-r-lg">Action</th>
        `;
    } else {
        document.querySelector('#screeners-view thead tr').innerHTML = `
            <th class="px-6 py-3 rounded-l-lg">Ticker</th>
            <th class="px-6 py-3">Signal / Reason</th>
            <th class="px-6 py-3 text-right">Price</th>
            <th class="px-6 py-3 text-right rounded-r-lg">Action</th>
        `;
    }

    const colspan = isInflation ? 7 : 4;
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="px-6 py-8 text-center text-warren-accent animate-pulse">Running Strategy Scan... (This may take 10s)</td></tr>`;

    title.textContent = `Results: ${names[strategyId] || 'Custom Scan'}`;

    try {
        const res = await fetch(`${API_BASE}/screeners/${strategyId}`);
        const payload = await res.json();

        const titleBadge = payload.universe_meta ? window.renderUniverseBadge(payload.universe_meta) : '';
        title.innerHTML = `Results: ${names[strategyId] || 'Custom Scan'} ${titleBadge}`;

        const data = Array.isArray(payload) ? payload : (payload.stocks || payload.results || []);

        tbody.innerHTML = '';

        if (data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${colspan}" class="px-6 py-8 text-center text-gray-400">No stocks in our universe matched this strict criteria.</td></tr>`;
            return;
        }

        data.forEach(stock => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-800/50 transition-colors border-b border-gray-800 last:border-0";

            if (isInflation) {
                const badge = _inflationBadge(stock.inflation_score || 0);
                const fcfVal = stock.fcf_yield != null ? parseFloat(stock.fcf_yield) : null;
                tr.innerHTML = `
                    <td class="px-4 py-3">
                        <div class="font-bold text-white">${linkTV(stock.symbol)}</div>
                        <div class="text-xs text-gray-500">${stock.name}</div>
                    </td>
                    <td class="px-4 py-3 text-center">
                        <div class="text-lg font-black text-white">${stock.inflation_score || 0}</div>
                        <span class="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border ${badge.cls}">${badge.label}</span>
                    </td>
                    <td class="px-4 py-3 text-right font-mono text-white">${stock.roe_pct != null ? stock.roe_pct + '%' : '--'}</td>
                    <td class="px-4 py-3 text-right font-mono text-white">${stock.debt_to_equity != null ? stock.debt_to_equity.toFixed(2) : '--'}</td>
                    <td class="px-4 py-3 text-right font-mono ${fcfVal != null && fcfVal >= 3 ? 'text-green-400' : 'text-white'}">${fcfVal != null ? fcfVal + '%' : '--'}</td>
                    <td class="px-4 py-3 text-right text-xs text-gray-400">${stock.sector || ''}</td>
                    <td class="px-4 py-3 text-right">
                        <button onclick="window.searchStock('${stock.symbol}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                            Analyze
                        </button>
                    </td>
                `;
            } else {
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
            }
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Screen failed", err);
        tbody.innerHTML = `<tr><td colspan="${colspan}" class="px-6 py-8 text-center text-red-400">Scan failed. Server may be busy.</td></tr>`;
    }
}
