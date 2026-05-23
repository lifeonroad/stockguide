import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

let CURRENT_SORT = { col: 'signal', dir: 'asc' };
let ZONE_FILTER = 'all';
let ZONE_RESULTS = [];

const ZONE_CONFIG = {
    crash: { color: 'text-emerald-300', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', label: 'Crash', icon: '💎' },
    dip: { color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30', label: 'Dip Zone', icon: '🟢' },
    early_accumulation: { color: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', label: 'Early Accumulation', icon: '🔷' },
    institutional: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30', label: 'Institutional', icon: '🔵' },
    public: { color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30', label: 'Public Zone', icon: '🟠' },
    extended: { color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30', label: 'Extended', icon: '🔴' },
};

const SIGNAL_CONFIG = {
    STRONG_BUY: { color: 'text-emerald-300', bg: 'bg-emerald-500/15', label: 'STRONG BUY' },
    BUY: { color: 'text-green-400', bg: 'bg-green-500/15', label: 'BUY' },
    ACCUMULATE: { color: 'text-cyan-400', bg: 'bg-cyan-500/15', label: 'ACCUMULATE' },
    HOLD: { color: 'text-yellow-400', bg: 'bg-yellow-500/15', label: 'HOLD' },
    EXIT: { color: 'text-red-400', bg: 'bg-red-500/15', label: 'EXIT' },
    NO_DATA: { color: 'text-gray-500', bg: 'bg-gray-500/15', label: 'NO DATA' },
};

const DETAILED_ZONE_ORDER = ['crash', 'dip', 'early_accumulation', 'institutional', 'public', 'extended'];

export async function loadTechnicalZones() {
    const container = document.getElementById('technical-zones-container');
    const header = document.getElementById('technical-zones-header');
    if (!container) return;

    header.innerHTML = '';
    container.innerHTML = '<div class="col-span-full text-center py-16 animate-pulse"><div class="text-warren-accent text-sm uppercase tracking-widest font-bold">Scanning Universe for Technical Zones...</div></div>';

    try {
        const res = await fetch(`${API_BASE}/technical/zones?zone=${ZONE_FILTER}`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        ZONE_RESULTS = data.results || [];
        renderFilterBar(data.count);
        renderTable();
    } catch (err) {
        console.error('Technical zones error:', err);
        container.innerHTML = `<div class="col-span-full text-center py-16 text-red-400">Failed to load: ${err.message}</div>`;
    }
}

function renderFilterBar(totalCount) {
    const header = document.getElementById('technical-zones-header');
    if (!header) return;

    const counts = { all: totalCount };
    DETAILED_ZONE_ORDER.forEach(z => {
        counts[z] = ZONE_RESULTS.filter(r => r.detailed_zone === z).length;
    });
    const legacyCounts = { dip: 0, institutional: 0, public: 0 };
    ZONE_RESULTS.forEach(r => {
        if (legacyCounts[r.zone] !== undefined) legacyCounts[r.zone]++;
    });

    header.innerHTML = `
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <h2 class="text-3xl font-bold text-white">Technical Zones</h2>
                <p class="text-gray-400 mt-1 text-sm">6-zone SMA 9/50/180 + RSI classification — actionable signals for accumulation, holding, and exit decisions.</p>
            </div>
            <div class="flex flex-wrap gap-1 bg-gray-900 p-1 rounded-lg border border-gray-800" id="zone-filter-bar">
                ${renderFilterButton('all', `All (${counts.all})`, ZONE_FILTER === 'all')}
                ${renderFilterButton('crash', `💎 Crash (${counts.crash||0})`, ZONE_FILTER === 'crash')}
                ${renderFilterButton('dip', `🟢 Dip (${counts.dip||0})`, ZONE_FILTER === 'dip')}
                ${renderFilterButton('early_accumulation', `🔷 Early Acc (${counts.early_accumulation||0})`, ZONE_FILTER === 'early_accumulation')}
                ${renderFilterButton('institutional', `🔵 Inst (${counts.institutional||0})`, ZONE_FILTER === 'institutional')}
                ${renderFilterButton('public', `🟠 Public (${counts.public||0})`, ZONE_FILTER === 'public')}
                ${renderFilterButton('extended', `🔴 Extended (${counts.extended||0})`, ZONE_FILTER === 'extended')}
            </div>
        </div>
        <div class="flex flex-wrap gap-2 mt-3">
            <span class="text-[10px] bg-emerald-500/10 text-emerald-300 px-2 py-0.5 rounded-full">Crash: Price < SMA 180 + RSI ≤ 25</span>
            <span class="text-[10px] bg-green-500/10 text-green-400 px-2 py-0.5 rounded-full">Dip: Price < SMA 180 + RSI > 25</span>
            <span class="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded-full">Early Acc: SMA 180 ≤ Price < SMA 50 + RSI < 40</span>
            <span class="text-[10px] bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full">Institutional: SMA 180 ≤ Price < SMA 50 + RSI ≥ 40</span>
            <span class="text-[10px] bg-orange-500/10 text-orange-400 px-2 py-0.5 rounded-full">Public: Price ≥ SMA 50 (below SMA 9, RSI ≤ 70)</span>
            <span class="text-[10px] bg-red-500/10 text-red-400 px-2 py-0.5 rounded-full">Extended: Price ≥ SMA 9 or RSI > 70</span>
        </div>
        <div class="flex flex-wrap gap-2 mt-1">
            <span class="text-[10px] text-gray-500">Legacy: Dip ${legacyCounts.dip} · Institutional ${legacyCounts.institutional} · Public ${legacyCounts.public}</span>
        </div>
    `;
}

function renderFilterButton(zone, label, active) {
    const activeClass = 'bg-warren-accent text-white';
    const inactiveClass = 'text-gray-400 hover:text-white';
    return `<button onclick="window.filterTechnicalZones('${zone}')" class="px-3 py-1 text-xs font-bold rounded transition-colors ${active ? activeClass : inactiveClass}">${label}</button>`;
}

export function filterTechnicalZones(zone) {
    ZONE_FILTER = zone;
    loadTechnicalZones();
}

function renderTable() {
    const container = document.getElementById('technical-zones-container');
    if (!container) return;

    if (ZONE_RESULTS.length === 0) {
        container.innerHTML = '<div class="col-span-full text-center py-16 text-gray-500">No tickers found in the selected zone.</div>';
        return;
    }

    const sortIndicator = (col) => {
        if (CURRENT_SORT.col !== col) return '↕';
        return CURRENT_SORT.dir === 'asc' ? '↑' : '↓';
    };

    const rows = ZONE_RESULTS.map(item => {
        const detailedCfg = ZONE_CONFIG[item.detailed_zone] || ZONE_CONFIG[item.zone] || {};
        const signalCfg = SIGNAL_CONFIG[item.signal] || SIGNAL_CONFIG.NO_DATA;
        const analyzeBtn = `<button onclick="window.searchStock('${item.symbol}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">Analyze</button>`;

        const zoneBadge = `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${detailedCfg.bg} ${detailedCfg.color} ${detailedCfg.border} border" title="Legacy zone: ${item.zone}">${detailedCfg.label}</span>`;
        const signalBadge = `<span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${signalCfg.bg} ${signalCfg.color}">${signalCfg.label}</span>`;

        return `<tr class="hover:bg-gray-700/30 transition-colors">
            <td class="px-4 py-3 font-medium text-white whitespace-nowrap">${linkTV(item.symbol)}</td>
            <td class="px-4 py-3 whitespace-nowrap">${zoneBadge}</td>
            <td class="px-4 py-3 whitespace-nowrap">${signalBadge}</td>
            <td class="px-4 py-3 font-mono text-gray-300 whitespace-nowrap">${item.action || '-'}</td>
            <td class="px-4 py-3 font-mono text-gray-300">$${item.price.toFixed(2)}</td>
            <td class="px-4 py-3 font-mono text-gray-500">${item.sma_9 != null ? '$' + item.sma_9.toFixed(2) : '-'}</td>
            <td class="px-4 py-3 font-mono text-gray-400">${item.sma_50 != null ? '$' + item.sma_50.toFixed(2) : '-'}</td>
            <td class="px-4 py-3 font-mono text-gray-400">${item.sma_180 != null ? '$' + item.sma_180.toFixed(2) : '-'}</td>
            <td class="px-4 py-3 font-mono ${item.rsi_14 < 30 ? 'text-green-400' : item.rsi_14 > 70 ? 'text-red-400' : 'text-gray-300'}">${item.rsi_14}</td>
            <td class="px-4 py-3 font-mono ${(item.pct_to_sma_50 || 0) < 0 ? 'text-green-400' : 'text-red-400'}">${item.pct_to_sma_50 != null ? item.pct_to_sma_50.toFixed(1) + '%' : '-'}</td>
            <td class="px-4 py-3 font-mono ${(item.pct_to_sma_180 || 0) < 0 ? 'text-green-400' : 'text-red-400'}">${item.pct_to_sma_180 != null ? item.pct_to_sma_180.toFixed(1) + '%' : '-'}</td>
            <td class="px-4 py-3 text-right whitespace-nowrap">${analyzeBtn}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
        <div class="glass-panel rounded-2xl overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full text-sm text-left">
                    <thead class="text-xs text-gray-400 uppercase bg-gray-800/50">
                        <tr>
                            <th class="px-4 py-4 cursor-pointer hover:text-white transition-colors whitespace-nowrap" onclick="window.sortTechnicalZones('symbol')">Ticker <span class="ml-1 text-[8px] opacity-50">${sortIndicator('symbol')}</span></th>
                            <th class="px-4 py-4 cursor-pointer hover:text-white transition-colors whitespace-nowrap" onclick="window.sortTechnicalZones('detailed_zone')">Zone <span class="ml-1 text-[8px] opacity-50">${sortIndicator('detailed_zone')}</span></th>
                            <th class="px-4 py-4 cursor-pointer hover:text-white transition-colors whitespace-nowrap" onclick="window.sortTechnicalZones('signal')">Signal <span class="ml-1 text-[8px] opacity-50">${sortIndicator('signal')}</span></th>
                            <th class="px-4 py-4 whitespace-nowrap">Action</th>
                            <th class="px-4 py-4 cursor-pointer hover:text-white transition-colors whitespace-nowrap" onclick="window.sortTechnicalZones('price')">Price <span class="ml-1 text-[8px] opacity-50">${sortIndicator('price')}</span></th>
                            <th class="px-4 py-4 whitespace-nowrap">SMA 9</th>
                            <th class="px-4 py-4 whitespace-nowrap">SMA 50</th>
                            <th class="px-4 py-4 whitespace-nowrap">SMA 180</th>
                            <th class="px-4 py-4 cursor-pointer hover:text-white transition-colors whitespace-nowrap" onclick="window.sortTechnicalZones('rsi_14')">RSI 14 <span class="ml-1 text-[8px] opacity-50">${sortIndicator('rsi_14')}</span></th>
                            <th class="px-4 py-4 whitespace-nowrap">% to SMA 50</th>
                            <th class="px-4 py-4 whitespace-nowrap">% to SMA 180</th>
                            <th class="px-4 py-4 text-right whitespace-nowrap">Action</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-700/50">
                        ${rows}
                    </tbody>
                </table>
            </div>
            <div class="px-4 py-3 bg-gray-900/50 border-t border-gray-700/50 text-[10px] text-gray-500">
                ${ZONE_RESULTS.length} ticker${ZONE_RESULTS.length !== 1 ? 's' : ''} · Sorted by signal strength · Prices reflect latest available close
            </div>
        </div>`;
}

export function sortTechnicalZones(col) {
    if (CURRENT_SORT.col === col) {
        CURRENT_SORT.dir = CURRENT_SORT.dir === 'asc' ? 'desc' : 'asc';
    } else {
        CURRENT_SORT.col = col;
        CURRENT_SORT.dir = 'asc';
    }

    const detailedOrder = { crash: 0, dip: 1, early_accumulation: 2, institutional: 3, public: 4, extended: 5, unknown: 99 };
    const signalOrder = { STRONG_BUY: 0, BUY: 1, ACCUMULATE: 2, HOLD: 3, EXIT: 4, NO_DATA: 5 };

    ZONE_RESULTS.sort((a, b) => {
        let va, vb;
        if (col === 'detailed_zone') {
            va = detailedOrder[a[col]] || 99;
            vb = detailedOrder[b[col]] || 99;
        } else if (col === 'signal') {
            va = signalOrder[a[col]] || 99;
            vb = signalOrder[b[col]] || 99;
        } else if (col === 'symbol') {
            va = a[col].toUpperCase();
            vb = b[col].toUpperCase();
        } else {
            va = a[col] || 0;
            vb = b[col] || 0;
        }
        if (va < vb) return CURRENT_SORT.dir === 'asc' ? -1 : 1;
        if (va > vb) return CURRENT_SORT.dir === 'asc' ? 1 : -1;
        return 0;
    });

    renderTable();
}

window.loadTechnicalZones = loadTechnicalZones;
window.filterTechnicalZones = filterTechnicalZones;
window.sortTechnicalZones = sortTechnicalZones;
