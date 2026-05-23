import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export let OPPORTUNITIES = [];
export let CURRENT_SORT_COL = 'drop_pct';
export let CURRENT_SORT_DIR = 'asc';
export let CURRENT_FILTER = 'All';

const OPPORTUNITY_TYPES = ['All', 'CRASH_BUY', 'COMPANY_TURNAROUND', 'SECTOR_RECOVERY', 'MOMENTUM_SHIFT', 'GENERIC_DIP'];

const TYPE_CONFIG = {
    CRASH_BUY: { color: 'red', icon: '🔴', label: 'Crash Buy' },
    COMPANY_TURNAROUND: { color: 'yellow', icon: '🔄', label: 'Turnaround' },
    SECTOR_RECOVERY: { color: 'cyan', icon: '📈', label: 'Sector Recovery' },
    MOMENTUM_SHIFT: { color: 'green', icon: '⚡', label: 'Momentum Shift' },
    GENERIC_DIP: { color: 'gray', icon: '📉', label: 'Generic Dip' },
};

const REGIME_CONFIG = {
    CRASH: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-400', icon: '🔴' },
    BEAR: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-400', icon: '🟠' },
    BULL: { bg: 'bg-green-500/10', border: 'border-green-500/30', text: 'text-green-400', icon: '🟢' },
    ROTATION: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', text: 'text-yellow-400', icon: '🟡' },
    MIXED: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-400', icon: '🔵' },
};

export async function loadDipHunterData() {
    const marketContainer = document.getElementById('market-etf-container');
    const sectorContainer = document.getElementById('sector-etf-container');
    if (!marketContainer) return;

    marketContainer.innerHTML = '<div class="col-span-full text-center py-10 text-warren-accent animate-pulse">Scanning Markets...</div>';
    sectorContainer.innerHTML = '<div class="text-center py-4 text-gray-500">Loading Sectors...</div>';

    try {
        const [summaryRes, etfsRes] = await Promise.all([
            fetch(`${API_BASE}/dip-hunter/summary`),
            fetch(`${API_BASE}/dip-hunter/etfs`),
        ]);
        const summary = await summaryRes.json();
        const etfs = await etfsRes.json();

        const lastUpdatedEl = document.getElementById('dip-last-updated');
        if (lastUpdatedEl && summary.last_updated) {
            lastUpdatedEl.textContent = `Last Scanned: ${new Date(summary.last_updated).toLocaleString()}`;
        }

        renderEtfs(etfs, marketContainer, sectorContainer);
        loadOpportunities(0);

    } catch (err) {
        console.error("Failed to load dip data", err);
    }
}

function renderEtfs(etfs, marketContainer, sectorContainer) {
    marketContainer.innerHTML = '';
    sectorContainer.innerHTML = '';

    etfs.forEach(etf => {
        const isBest = etf.classification === 'BEST';
        const isBetter = etf.classification === 'BETTER';
        const isGood = etf.classification === 'GOOD';

        const badgeColor = isBest ? 'bg-green-500/20 text-green-400 border-green-500/30' :
            isBetter ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' :
                isGood ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' :
                    'bg-gray-800 text-gray-500 border-gray-700';

        const dropColor = etf.drop_pct < -10 ? 'text-red-400' : etf.drop_pct < -5 ? 'text-orange-400' : 'text-yellow-400';

        if (etf.is_market_etf) {
            const card = document.createElement('div');
            card.className = "glass-panel p-5 rounded-xl border border-gray-700/50 flex flex-col justify-between";
            card.innerHTML = `
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <div class="font-bold text-white text-lg">${etf.ticker}</div>
                        <div class="text-[10px] text-gray-500 uppercase">${etf.name}</div>
                    </div>
                    <span class="px-2 py-0.5 rounded border text-[10px] font-bold ${badgeColor}">${etf.classification}</span>
                </div>
                <div class="flex items-end justify-between">
                    <div>
                        <div class="text-3xl font-black ${dropColor}">${etf.drop_pct}%</div>
                        <div class="text-[10px] text-gray-500 uppercase tracking-widest mt-1">From 52W High</div>
                    </div>
                    <div class="text-right">
                         <div class="text-xs text-gray-400">RSI: <span class="${etf.rsi < 35 ? 'text-green-400 font-bold' : 'text-white'}">${etf.rsi}</span></div>
                         <div class="text-[10px] text-gray-500">Vol: ${etf.volume_ratio}x</div>
                    </div>
                </div>
            `;
            marketContainer.appendChild(card);
        } else {
            if (Math.abs(etf.drop_pct) < 3) return;

            const card = document.createElement('div');
            card.className = "flex-shrink-0 w-40 glass-panel p-3 rounded-lg border border-gray-800 hover:border-gray-700 transition-all";
            card.innerHTML = `
                <div class="flex justify-between items-center mb-1">
                    <span class="text-xs font-bold text-white">${etf.ticker}</span>
                    <span class="text-[9px] ${dropColor} font-bold">${etf.drop_pct}%</span>
                </div>
                <div class="text-[9px] text-gray-600 truncate mb-2">${etf.name}</div>
                <div class="h-1 w-full bg-gray-800 rounded-full overflow-hidden">
                    <div class="h-full bg-warren-accent" style="width: ${Math.min(Math.abs(etf.drop_pct) * 5, 100)}%"></div>
                </div>
            `;
            sectorContainer.appendChild(card);
        }
    });
}

export async function loadOpportunities(minQuality = 0) {
    const tbody = document.getElementById('dip-stocks-body');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-8 text-center text-warren-accent animate-pulse">Analyzing Opportunities...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/opportunities?min_quality=${minQuality}`);
        const data = await res.json();

        OPPORTUNITIES = data.opportunities || [];

        renderRegimeBanner(data.regime);
        renderFilterBar(data.summary);
        renderOpportunities();

    } catch (err) {
        console.error("Failed to load opportunities", err);
        tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-8 text-center text-red-400">Scan failed. Try again later.</td></tr>';
    }
}

function renderRegimeBanner(regime) {
    let bannerEl = document.getElementById('regime-banner');
    if (!bannerEl) {
        bannerEl = document.createElement('div');
        bannerEl.id = 'regime-banner';
        const headerEl = document.querySelector('#diphunter-view .text-center');
        if (headerEl) {
            headerEl.after(bannerEl);
        }
    }

    const cfg = REGIME_CONFIG[regime.regime] || REGIME_CONFIG.MIXED;

    bannerEl.className = `glass-panel p-4 rounded-xl border ${cfg.border} ${cfg.bg}`;
    bannerEl.innerHTML = `
        <div class="flex items-center justify-between flex-wrap gap-4">
            <div class="flex items-center gap-3">
                <span class="text-2xl">${cfg.icon}</span>
                <div>
                    <div class="font-bold text-white text-lg ${cfg.text}">${regime.regime} MARKET</div>
                    <div class="text-xs text-gray-400">${regime.signal}</div>
                </div>
            </div>
            <div class="flex gap-6 text-sm">
                <div class="text-center">
                    <div class="text-[10px] text-gray-500 uppercase">SPY</div>
                    <div class="font-bold ${regime.spy_drop < -5 ? 'text-red-400' : 'text-white'}">${regime.spy_drop}%</div>
                </div>
                <div class="text-center">
                    <div class="text-[10px] text-gray-500 uppercase">QQQ</div>
                    <div class="font-bold ${regime.qqq_drop < -5 ? 'text-red-400' : 'text-white'}">${regime.qqq_drop}%</div>
                </div>
                <div class="text-center">
                    <div class="text-[10px] text-gray-500 uppercase">Breadth</div>
                    <div class="font-bold ${regime.breadth < 40 ? 'text-red-400' : regime.breadth > 60 ? 'text-green-400' : 'text-white'}">${regime.breadth}%</div>
                </div>
            </div>
        </div>
    `;
}

function renderFilterBar(summary) {
    let barEl = document.getElementById('opportunity-filter-bar');
    if (!barEl) {
        barEl = document.createElement('div');
        barEl.id = 'opportunity-filter-bar';
        const tableHeader = document.querySelector('#diphunter-view .glass-panel .p-6');
        if (tableHeader) {
            tableHeader.before(barEl);
        }
    }

    const total = summary.total || 0;
    const byType = summary.by_type || {};

    barEl.className = "flex gap-2 overflow-x-auto pb-2";
    barEl.innerHTML = OPPORTUNITY_TYPES.map(type => {
        const cfg = TYPE_CONFIG[type];
        const count = type === 'All' ? total : (byType[type] || 0);
        const isActive = CURRENT_FILTER === type;
        const colorClass = isActive ?
            (type === 'All' ? 'bg-warren-accent/20 text-warren-accent border-warren-accent/40' : `bg-${cfg.color}-500/20 text-${cfg.color}-400 border-${cfg.color}-500/40`) :
            'bg-gray-800/50 text-gray-400 border-gray-700 hover:border-gray-600';

        return `<button onclick="window.filterOpportunities('${type}')"
            class="flex-shrink-0 text-xs px-3 py-1.5 rounded-lg border transition-all ${colorClass}">
            ${cfg ? cfg.icon : ''} ${cfg ? cfg.label : 'All'} <span class="opacity-60">(${count})</span>
        </button>`;
    }).join('');
}

window.filterOpportunities = function(type) {
    CURRENT_FILTER = type;
    renderOpportunities();

    document.querySelectorAll('#opportunity-filter-bar button').forEach(btn => {
        const isActive = btn.textContent.includes(type === 'All' ? 'All' : TYPE_CONFIG[type]?.label || '');
        if (isActive) {
            const cfg = type === 'All' ?
                { color: 'warren-accent' } :
                TYPE_CONFIG[type] || { color: 'gray' };
            btn.className = `flex-shrink-0 text-xs px-3 py-1.5 rounded-lg border transition-all bg-${cfg.color}-500/20 text-${cfg.color}-400 border-${cfg.color}-500/40`;
        } else {
            btn.className = 'flex-shrink-0 text-xs px-3 py-1.5 rounded-lg border transition-all bg-gray-800/50 text-gray-400 border-gray-700 hover:border-gray-600';
        }
    });
};

function renderOpportunities() {
    const tbody = document.getElementById('dip-stocks-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    let filtered = CURRENT_FILTER === 'All' ?
        OPPORTUNITIES :
        OPPORTUNITIES.filter(o => o.opportunity_type === CURRENT_FILTER);

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-8 text-center text-gray-500">No opportunities match this filter.</td></tr>';
        return;
    }

    const data = [...filtered].sort((a, b) => {
        let valA = a[CURRENT_SORT_COL];
        let valB = b[CURRENT_SORT_COL];

        if (CURRENT_SORT_COL === 'classification' || CURRENT_SORT_COL === 'opportunity_type') {
            const tiers = { 'BEST': 3, 'BETTER': 2, 'GOOD': 1, 'NONE': 0 };
            valA = tiers[valA] || 0;
            valB = tiers[valB] || 0;
        }

        if (valA < valB) return CURRENT_SORT_DIR === 'asc' ? -1 : 1;
        if (valA > valB) return CURRENT_SORT_DIR === 'asc' ? 1 : -1;
        return 0;
    });

    data.forEach(stock => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-gray-800/30 transition-colors border-b border-gray-800/50";

        const dropColor = stock.drop_pct < -10 ? 'text-red-400 font-bold' : 'text-orange-400';
        const rsiColor = stock.rsi < 35 ? 'text-green-400 font-bold' : 'text-gray-300';

        const isBest = stock.classification === 'BEST';
        const isBetter = stock.classification === 'BETTER';
        const badgeColor = isBest ? 'bg-green-500/20 text-green-400' :
            isBetter ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-orange-500/20 text-orange-400';

        const oppType = stock.opportunity_type || 'GENERIC_DIP';
        const typeCfg = TYPE_CONFIG[oppType] || TYPE_CONFIG.GENERIC_DIP;
        const typeBadgeColor = `bg-${typeCfg.color}-500/20 text-${typeCfg.color}-400 border-${typeCfg.color}-500/30`;

        const signalsHtml = stock.signals && stock.signals.length > 0 ?
            stock.signals.map(s => `<span class="inline-block text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 mr-1">${s}</span>`).join('') : '';

        tr.innerHTML = `
            <td class="px-6 py-4">
                <div class="font-bold text-white">${linkTV(stock.ticker)}</div>
                <div class="text-[10px] text-gray-500">${stock.name || ''}</div>
                ${stock.sector === 'Tracked' ? '<div class="text-[9px] text-warren-accent px-1 border border-warren-accent/30 rounded inline-block mt-1">OWNED</div>' : ''}
            </td>
            <td class="px-6 py-4 ${dropColor}">${stock.drop_pct}%</td>
            <td class="px-6 py-4 ${rsiColor}">${stock.rsi}</td>
            <td class="px-6 py-4 text-gray-300">${stock.roe}%</td>
            <td class="px-6 py-4 text-gray-300">${stock.debt_equity}</td>
            <td class="px-6 py-4">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${badgeColor}">${stock.classification}</span>
            </td>
            <td class="px-6 py-4">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${typeBadgeColor}">${typeCfg.icon} ${typeCfg.label}</span>
            </td>
            <td class="px-6 py-4 max-w-[200px]">
                <div class="text-[10px] text-gray-400 line-clamp-2" title="${stock.thesis || ''}">${stock.thesis || ''}</div>
                <div class="flex flex-wrap mt-1 gap-0.5">${signalsHtml}</div>
            </td>
            <td class="px-6 py-4 text-right">
                <button onclick="window.searchStock('${stock.ticker}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                    Analyze
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

export function sortDipStocks(column) {
    if (CURRENT_SORT_COL === column) {
        CURRENT_SORT_DIR = CURRENT_SORT_DIR === 'asc' ? 'desc' : 'asc';
    } else {
        CURRENT_SORT_COL = column;
        CURRENT_SORT_DIR = 'asc';
    }

    const cols = ['ticker', 'drop_pct', 'rsi', 'roe', 'debt_equity', 'classification'];
    cols.forEach(c => {
        const span = document.getElementById(`sort-${c}`);
        if (span) {
            span.textContent = CURRENT_SORT_COL === c ? (CURRENT_SORT_DIR === 'asc' ? '↑' : '↓') : '↕';
            span.style.opacity = CURRENT_SORT_COL === c ? '1' : '0.5';
        }
    });

    renderOpportunities();
}

// Attach to window for HTML onclick handlers
window.loadOpportunities = loadOpportunities;
window.sortDipStocks = sortDipStocks;
