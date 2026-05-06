import { API_BASE } from '../api.js';
import { formatCurrency } from '../utils.js';

export let MACRO_DATA = null;

export async function loadMarketStatus() {
    try {
        const res = await fetch(`${API_BASE}/market-status`);
        const data = await res.json();

        document.getElementById('buffett-ratio').textContent = `${data.ratio_percent}%`;
        document.getElementById('market-cap-val').textContent = formatCurrency(data.market_cap);
        document.getElementById('gdp-val').textContent = formatCurrency(data.gdp);

        const badge = document.getElementById('buffett-status-badge');
        badge.textContent = data.rating;

        let colorClass = 'bg-gray-500';

        if (data.rating.includes('Undervalued')) {
            colorClass = 'bg-warren-success';
            badge.className = `text-xl font-semibold px-4 py-1 rounded-full bg-green-500/20 text-green-400`;
        } else if (data.rating.includes('Fair')) {
            colorClass = 'bg-warren-warning';
            badge.className = `text-xl font-semibold px-4 py-1 rounded-full bg-yellow-500/20 text-yellow-400`;
        } else {
            colorClass = 'bg-warren-danger';
            badge.className = `text-xl font-semibold px-4 py-1 rounded-full bg-red-500/20 text-red-400`;
        }

        const maxScale = 200;
        const widthPct = Math.min((data.ratio_percent / maxScale) * 100, 100);

        const gaugeFill = document.getElementById('gauge-fill');
        gaugeFill.style.width = `${widthPct}%`;
        gaugeFill.className = `h-full transition-all duration-1000 ease-out w-0 ${colorClass}`;

    } catch (err) {
        console.error("Failed to load market status", err);
    }
}

export async function loadMacroTrends() {
    try {
        const res = await fetch(`${API_BASE}/macro`);
        const data = await res.json();
        MACRO_DATA = data;

        const container = document.getElementById('macro-container');
        container.innerHTML = '';

        const indicators = [
            { id: 'rates', label: '10Y Treasury', val: `${data.indicators.rates.current}%`, change: data.indicators.rates.change_pct, icon: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6' },
            { id: 'oil', label: 'Crude Oil', val: `$${data.indicators.oil.current}`, change: data.indicators.oil.change_pct, icon: 'M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z' },
            { id: 'gold', label: 'Gold', val: `$${data.indicators.gold.current}`, change: data.indicators.gold.change_pct, icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
            { id: 'vix', label: 'VIX (Fear)', val: data.indicators.vix.current, change: data.indicators.vix.change_pct, icon: 'M13 10V3L4 14h7v7l9-11h-7z' },
        ];

        indicators.forEach(ind => {
            const isUp = ind.change > 0;
            const color = isUp ? 'text-green-400' : 'text-red-400';

            const div = document.createElement('div');
            div.className = "glass-panel p-4 rounded-xl flex flex-col justify-between";
            div.innerHTML = `
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs text-gray-400 uppercase">${ind.label}</span>
                    <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${ind.icon}"></path></svg>
                </div>
                <div>
                    <div class="text-xl font-mono text-white">${ind.val}</div>
                    <div class="text-xs ${color}">${isUp ? '+' : ''}${ind.change}% (5d)</div>
                </div>
            `;
            container.appendChild(div);
        });

    } catch (err) {
        console.error("Failed to load macro", err);
    }
}
