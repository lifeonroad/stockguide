import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export async function loadAlphaIntelligence() {
    console.log("Loading Alpha Intelligence...");
    try {
        const res = await fetch(`${API_BASE}/alpha/cycle`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        renderCyclePhase(data.phase);
        renderRotationTable(data.rotation);

    } catch (err) {
        console.error("Alpha Intelligence Scan Failed", err);
    }
}

function renderCyclePhase(phase) {
    const nameEl = document.getElementById('cycle-phase-name');
    const badgeEl = document.getElementById('cycle-phase-badge');
    const descEl = document.getElementById('cycle-phase-desc');
    const borderEl = document.getElementById('cycle-phase-border');
    const focusEl = document.getElementById('cycle-focus');
    const riskDial = document.getElementById('risk-dial');
    const riskLabel = document.getElementById('risk-label');

    if (!nameEl) return;

    nameEl.textContent = phase.name;
    badgeEl.textContent = phase.name;
    descEl.textContent = phase.description;

    const colors = {
        'green': { border: 'border-green-500', badge: 'bg-green-500/20 text-green-400', focus: 'Cyclicals, Tech, Small Caps', sentiment: 'Aggressive Accumulation', risk: '🛡️', riskLabel: 'Low Risk Regime' },
        'blue': { border: 'border-blue-500', badge: 'bg-blue-500/20 text-blue-400', focus: 'Quality Growth, Healthcare', sentiment: 'Calculated Risk Taking', risk: '⚖️', riskLabel: 'Moderate Risk' },
        'orange': { border: 'border-orange-500', badge: 'bg-orange-500/20 text-orange-400', focus: 'Staples, Utilities, Energy', sentiment: 'Defensive Distribution', risk: '⚠️', riskLabel: 'High Risk Warning' },
        'red': { border: 'border-red-500', badge: 'bg-red-500/20 text-red-400', focus: 'Cash, Gold, Inverse ETFs', sentiment: 'Panic / Capitulation', risk: '🚨', riskLabel: 'Extreme Risk' }
    };

    const config = colors[phase.color] || colors['blue'];

    borderEl.className = `glass-panel p-6 rounded-2xl col-span-2 border-l-4 ${config.border}`;
    badgeEl.className = `px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${config.badge}`;

    focusEl.textContent = config.focus;
    document.getElementById('cycle-hint').textContent = phase.hint || config.sentiment;
    riskDial.textContent = config.risk;
    riskLabel.textContent = config.riskLabel;
}

function renderRotationTable(rotation) {
    const tbody = document.getElementById('rotation-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    rotation.forEach(s => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-gray-800/30 transition-colors border-b border-gray-800/50";

        const getPerfClass = (val) => val >= 0 ? 'text-green-400' : 'text-red-400';
        const formatPct = (val) => `${val > 0 ? '+' : ''}${parseFloat(val || 0).toFixed(2)}%`;
        const perf1M = s.returns ? (s.returns['1M'] || 0) : 0;

        const rating = s.rating || 'HOLD';
        let ratingClass = 'text-gray-400';
        if (rating.includes('BUY')) ratingClass = 'text-green-400';
        if (rating.includes('SELL')) ratingClass = 'text-red-400';

        const picks = s.top_picks || [];
        const picksHtml = picks.map(ticker => linkTV(ticker)).join(' ');

        tr.innerHTML = `
            <td class="px-6 py-4">
                <div class="font-bold text-white">${s.name}</div>
                <div class="text-[10px] text-gray-500 uppercase">${s.ticker}</div>
            </td>
            <td class="px-6 py-4 text-center font-mono ${getPerfClass(s.returns['1D'])} text-xs">${formatPct(s.returns['1D'])}</td>
            <td class="px-6 py-4 text-center font-mono ${getPerfClass(s.returns['1W'])} text-xs">${formatPct(s.returns['1W'])}</td>
            <td class="px-6 py-4 text-center bg-warren-accent/5">
                <div class="flex items-center justify-center gap-2">
                    <span class="font-mono font-bold ${getPerfClass(perf1M)} text-xs">${formatPct(perf1M)}</span>
                    <div class="h-1 w-12 bg-gray-800 rounded-full overflow-hidden hidden md:block">
                        <div class="h-full bg-warren-accent" style="width: ${Math.min(Math.abs(perf1M) * 5, 100)}%"></div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 text-center font-mono ${getPerfClass(s.returns['6M'])} text-xs">${formatPct(s.returns['6M'])}</td>
            <td class="px-6 py-4 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${ratingClass} border-current opacity-80 uppercase tracking-tighter">
                    ${s.rating}
                </span>
            </td>
            <td class="px-6 py-4">
                <div class="flex flex-wrap gap-1">
                    ${picksHtml || '<span class="text-gray-600 text-[10px]">Analyzing...</span>'}
                </div>
            </td>
            <td class="px-6 py-4 text-right">
                <span class="text-lg font-black text-white">${Math.round((s.momentum_score || 0) + 50)}</span>
                <span class="text-[10px] text-gray-500">pts</span>
            </td>
        `;
        tbody.appendChild(tr);
    });
}
