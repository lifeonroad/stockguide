import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export async function loadTickerSignals(symbol, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '<div class="text-xs text-gray-500 animate-pulse">Loading signals...</div>';

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);
        const res = await fetch(`${API_BASE}/ticker-signals/${symbol}`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<div class="text-xs text-gray-500">${data.error}</div>`;
            return;
        }

        const overall = data.overall || {};
        const signalColors = {
            'Strong Buy': 'bg-green-500/20 text-green-300 border-green-500/30',
            'Buy': 'bg-green-500/10 text-green-400 border-green-500/20',
            'Hold': 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
            'Sell': 'bg-red-500/10 text-red-400 border-red-500/20',
            'Strong Sell': 'bg-red-500/20 text-red-300 border-red-500/30',
        };
        const signalCls = signalColors[overall.signal] || 'bg-gray-700 text-gray-400';

        let html = `
        <div class="bg-gray-900/60 rounded-xl border border-gray-700 p-4">
            <div class="flex items-center justify-between mb-3">
                <h4 class="text-sm font-semibold text-white">${linkTV(symbol)} Entry/Exit Signals</h4>
                <span class="text-xs font-bold px-2 py-1 rounded border ${signalCls}">${overall.signal || '--'}</span>
            </div>
            <div class="text-xs text-gray-500 mb-3">${overall.detail || ''}</div>
            <div class="grid grid-cols-2 gap-4 mb-3">
                <div>
                    <div class="text-xs text-gray-500 mb-1">Price</div>
                    <div class="text-lg font-bold text-white">$${data.current_price}</div>
                </div>
                <div class="text-right">
                    <div class="text-xs text-gray-500 mb-1">Risk/Reward</div>
                    <div class="text-lg font-bold ${data.risk_reward_ratio >= 2 ? 'text-green-400' : data.risk_reward_ratio >= 1 ? 'text-yellow-400' : 'text-gray-400'}">${data.risk_reward_ratio ? data.risk_reward_ratio + ':1' : '--'}</div>
                </div>
            </div>`;

        if (data.entry_zone && data.entry_zone.length > 0) {
            html += `
            <div class="mb-2">
                <div class="text-xs font-semibold text-green-400 mb-1 uppercase tracking-wider">Entry Zone</div>
                <div class="space-y-1">`;
            data.entry_zone.forEach(e => {
    const cls = e.distance_pct < 5 ? 'text-green-300' : 'text-green-400';
    html += `
        <div class="flex flex-col text-xs bg-gray-800/50 rounded px-2 py-1">
            <span class="${cls}">(${e.distance_pct}%)</span>
            <div class="flex justify-between">
                <span class="text-gray-400">${e.level}</span>
                <span>$${e.price}</span>
            </div>
        </div>`;
});
            html += `</div></div>`;
        }

        if (data.exit_zone && data.exit_zone.length > 0) {
            html += `
                <div class="mb-2">
                    <div class="text-xs font-semibold text-red-400 mb-1 uppercase tracking-wider">Exit Zone</div>
                    <div class="space-y-1">`;
            data.exit_zone.forEach(e => {
                html += `
<div class="flex flex-col text-xs bg-gray-800/50 rounded px-2 py-1">
    <div class="flex justify-between">
        <span class="text-gray-400">${e.level}</span>
        <span>$${e.price}</span>
    </div>
    <span class="text-red-400">(${e.distance_pct}%)</span>
</div>`;
            });
            html += `</div></div>`;
        }

        if (data.signals && data.signals.length > 0) {
            html += `
            <div>
                <div class="text-xs font-semibold text-gray-300 mb-1 uppercase tracking-wider">Active Signals</div>
                <div class="flex flex-wrap gap-1">`;
            data.signals.forEach(s => {
                const cls = s.type === 'entry' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20';
                const prefix = s.type === 'entry' ? '← ' : '→ ';
                const tag = s.strength === 'strong' ? `<span class="text-[9px] ml-1 font-bold">✦</span>` : '';
                html += `<span class="text-[10px] px-1.5 py-0.5 rounded border ${cls}">${prefix}${s.source}${tag}</span>`;
            });
            html += `</div></div>`;
        }

        html += `</div>`;
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = `<div class="text-xs text-gray-500">Signals unavailable</div>`;
    }
}
