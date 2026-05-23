import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

const SIGNAL_CONFIG = {
    STRONG_BUY: { color: 'text-emerald-300', bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', label: 'STRONG BUY', icon: '🟢' },
    BUY: { color: 'text-green-400', bg: 'bg-green-500/15', border: 'border-green-500/30', label: 'BUY', icon: '📗' },
    WATCH: { color: 'text-yellow-400', bg: 'bg-yellow-500/15', border: 'border-yellow-500/30', label: 'WATCH', icon: '🟡' },
    HOLD: { color: 'text-orange-400', bg: 'bg-orange-500/15', border: 'border-orange-500/30', label: 'HOLD', icon: '🟠' },
    AVOID: { color: 'text-red-400', bg: 'bg-red-500/15', border: 'border-red-500/30', label: 'AVOID', icon: '🔴' },
};

let CURRENT_SORT = { col: 'momentum_score', dir: 'desc' };
let MOMENTUM_RESULTS = [];

export async function loadMomentumData() {
    const container = document.getElementById('momentum-container');
    const header = document.getElementById('momentum-header');
    if (!container) return;

    header.innerHTML = '';
    container.innerHTML = '<div class="text-center py-16 animate-pulse"><div class="text-warren-accent text-sm uppercase tracking-widest font-bold">Scanning Universe for Momentum Picks...</div></div>';

    try {
        const res = await fetch(`${API_BASE}/momentum?min_score=0&limit=50`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        MOMENTUM_RESULTS = data.picks || [];
        renderHeader(data.count);
        renderTable();
    } catch (err) {
        console.error('Momentum scan error:', err);
        container.innerHTML = `<div class="text-center py-16 text-red-400">Failed to load momentum data: ${err.message}</div>`;
    }
}

function renderHeader(count) {
    const header = document.getElementById('momentum-header');
    if (!header) return;

    header.innerHTML = `
        <div class="glass-panel p-6 rounded-2xl bg-gradient-to-r from-gray-900 via-gray-800 to-gray-900 border border-warren-accent/20">
            <div class="flex flex-col md:flex-row items-center justify-between gap-4">
                <div>
                    <h2 class="text-2xl font-black text-white tracking-tight">Momentum Investing <span class="text-warren-accent">⚡</span></h2>
                    <p class="text-xs text-gray-500 uppercase font-bold tracking-widest mt-1">
                        ${count} stocks ranked by multi-factor momentum score
                    </p>
                </div>
                <div class="flex items-center gap-3 text-sm">
                    <span class="text-gray-400">Sort:</span>
                    <select onchange="window.sortMomentum(this.value)" class="bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm">
                        <option value="score">Score</option>
                        <option value="roc_1m">1M ROC</option>
                        <option value="roc_6m">6M ROC</option>
                        <option value="rsi">RSI</option>
                        <option value="adx">ADX</option>
                    </select>
                </div>
            </div>
        </div>
    `;

    window.sortMomentum = (key) => {
        const sortMap = {
            score: { col: 'momentum_score', dir: 'desc' },
            roc_1m: { col: 'roc_1m', dir: 'desc' },
            roc_6m: { col: 'roc_6m', dir: 'desc' },
            rsi: { col: 'rsi_14', dir: 'desc' },
            adx: { col: 'adx', dir: 'desc' },
        };
        CURRENT_SORT = sortMap[key] || sortMap.score;
        renderTable();
    };
}

function renderTable() {
    const container = document.getElementById('momentum-container');
    if (!container) return;

    const sorted = [...MOMENTUM_RESULTS].sort((a, b) => {
        const av = a[CURRENT_SORT.col] ?? 0;
        const bv = b[CURRENT_SORT.col] ?? 0;
        return CURRENT_SORT.dir === 'desc' ? bv - av : av - bv;
    });

    if (sorted.length === 0) {
        container.innerHTML = '<div class="text-center py-16 text-gray-400">No momentum picks found. Try lowering the minimum score.</div>';
        return;
    }

    let rows = '';
    sorted.forEach((p, i) => {
        const sig = SIGNAL_CONFIG[p.signal] || SIGNAL_CONFIG.HOLD;
        const scoreColor = p.momentum_score >= 80 ? 'text-emerald-300' :
            p.momentum_score >= 65 ? 'text-green-400' :
            p.momentum_score >= 50 ? 'text-yellow-400' :
            p.momentum_score >= 25 ? 'text-orange-400' : 'text-red-400';

        const reasons = (p.reasons || []).slice(0, 2).map(r =>
            `<span class="text-[10px] px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 border border-gray-700">${r}</span>`
        ).join('');

        const tvLink = linkTV(p.symbol);

        rows += `
            <tr class="hover:bg-gray-800/30 transition-colors border-b border-gray-800/50">
                <td class="py-3 px-4 text-sm font-mono text-white font-bold">${i + 1}</td>
                <td class="py-3 px-4">${tvLink}</td>
                <td class="py-3 px-4">
                    <span class="text-sm font-bold font-mono ${scoreColor}">${p.momentum_score.toFixed(1)}</span>
                </td>
                <td class="py-3 px-4">
                    <span class="text-xs font-bold px-2 py-0.5 rounded-full ${sig.bg} ${sig.color} border ${sig.border}">${sig.icon} ${sig.label}</span>
                </td>
                <td class="py-3 px-4 text-sm font-mono text-gray-300">$${p.price?.toFixed(2) ?? '—'}</td>
                <td class="py-3 px-4 text-sm font-mono ${p.roc_1m >= 0 ? 'text-green-400' : 'text-red-400'}">${p.roc_1m != null ? p.roc_1m.toFixed(1) + '%' : '—'}</td>
                <td class="py-3 px-4 text-sm font-mono ${p.roc_6m >= 0 ? 'text-green-400' : 'text-red-400'}">${p.roc_6m != null ? p.roc_6m.toFixed(1) + '%' : '—'}</td>
                <td class="py-3 px-4 text-sm font-mono text-gray-300">${p.rsi_14?.toFixed(1) ?? '—'}</td>
                <td class="py-3 px-4 text-sm font-mono text-gray-300">${p.adx?.toFixed(1) ?? '—'}</td>
                <td class="py-3 px-4 text-sm font-mono ${p.golden_cross ? 'text-green-400' : 'text-gray-500'}">${p.golden_cross ? '✓' : '—'}</td>
                <td class="py-3 px-4 text-sm font-mono text-gray-300">${p.volume_ratio?.toFixed(2) ?? '—'}</td>
                <td class="py-3 px-4">${reasons}</td>
            </tr>`;
    });

    container.innerHTML = `
        <div class="glass-panel rounded-2xl overflow-hidden border border-gray-800">
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead>
                        <tr class="text-xs uppercase tracking-wider text-gray-500 border-b border-gray-800">
                            <th class="py-3 px-4 text-left font-bold">#</th>
                            <th class="py-3 px-4 text-left font-bold">Symbol</th>
                            <th class="py-3 px-4 text-left font-bold">Score</th>
                            <th class="py-3 px-4 text-left font-bold">Signal</th>
                            <th class="py-3 px-4 text-left font-bold">Price</th>
                            <th class="py-3 px-4 text-left font-bold">1M ROC</th>
                            <th class="py-3 px-4 text-left font-bold">6M ROC</th>
                            <th class="py-3 px-4 text-left font-bold">RSI</th>
                            <th class="py-3 px-4 text-left font-bold">ADX</th>
                            <th class="py-3 px-4 text-left font-bold">Golden X</th>
                            <th class="py-3 px-4 text-left font-bold">Vol Ratio</th>
                            <th class="py-3 px-4 text-left font-bold">Reasons</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="p-4 border-t border-gray-800 bg-gray-900/30 text-xs text-gray-500">
                <span class="font-bold text-warren-accent">${MOMENTUM_RESULTS.length}</span> picks shown — sorted by ${CURRENT_SORT.col.replace(/_/g, ' ')}
            </div>
        </div>
    `;
}
