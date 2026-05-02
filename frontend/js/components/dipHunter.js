import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export let DIP_STOCKS = [];
export let CURRENT_SORT_COL = 'drop_pct';
export let CURRENT_SORT_DIR = 'asc'; // asc means more negative for drop_pct (better dip)

export async function loadDipHunterData() {
    const marketContainer = document.getElementById('market-etf-container');
    const sectorContainer = document.getElementById('sector-etf-container');
    if (!marketContainer) return;

    marketContainer.innerHTML = '<div class="col-span-full text-center py-10 text-warren-accent animate-pulse">Scanning Major Markets...</div>';
    sectorContainer.innerHTML = '<div class="text-center py-4 text-gray-500">Loading Sectors...</div>';

    try {
        const summaryRes = await fetch(`${API_BASE}/dip-hunter/summary`);
        const summary = await summaryRes.json();
        const lastUpdatedEl = document.getElementById('dip-last-updated');
        if (lastUpdatedEl && summary.last_updated) {
            lastUpdatedEl.textContent = `Last Scanned: ${new Date(summary.last_updated).toLocaleString()}`;
        }

        const res = await fetch(`${API_BASE}/dip-hunter/etfs`);
        const etfs = await res.json();

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

        loadDipStocks(0);

    } catch (err) {
        console.error("Failed to load dip data", err);
    }
}

export async function loadDipStocks(minQuality = 0) {
    const tbody = document.getElementById('dip-stocks-body');
    const badgeEl = document.getElementById('dip-universe-badge');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="9" class="px-6 py-8 text-center text-warren-accent animate-pulse">Filtering Quality Opportunities...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/dip-hunter/stocks?min_quality=${minQuality}`);
        const payload = await res.json();

        DIP_STOCKS = Array.isArray(payload) ? payload : (payload.results || []);

        if (badgeEl && payload.universe_meta) {
            badgeEl.innerHTML = window.renderUniverseBadge(payload.universe_meta);
        }

        renderDipStocks();

    } catch (err) {
        console.error("Failed to load dip stocks", err);
        tbody.innerHTML = '<tr><td colspan="9" class="px-6 py-8 text-center text-red-400">Scan failed.</td></tr>';
    }
}

function renderDipStocks() {
    const tbody = document.getElementById('dip-stocks-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (DIP_STOCKS.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="px-6 py-8 text-center text-gray-500">No high-quality stocks matched the dip criteria right now.</td></tr>';
        return;
    }

    const data = [...DIP_STOCKS].sort((a, b) => {
        let valA = a[CURRENT_SORT_COL];
        let valB = b[CURRENT_SORT_COL];

        if (CURRENT_SORT_COL === 'classification') {
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
        const rec5Color = stock.recovery_5d > 5 ? 'text-green-400 font-bold' : (stock.recovery_5d > 0 ? 'text-gray-300' : 'text-red-400 opacity-80');
        const rec15Color = stock.recovery_15d > 5 ? 'text-green-400 font-bold' : (stock.recovery_15d > 0 ? 'text-gray-300' : 'text-red-400 opacity-80');
        const rsiColor = stock.rsi < 35 ? 'text-green-400 font-bold' : 'text-gray-300';

        const isBest = stock.classification === 'BEST';
        const isBetter = stock.classification === 'BETTER';
        const badgeColor = isBest ? 'bg-green-500/20 text-green-400' :
            isBetter ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-orange-500/20 text-orange-400';

        tr.innerHTML = `
            <td class="px-6 py-4">
                <div class="font-bold text-white">${linkTV(stock.ticker)}</div>
                <div class="text-[10px] text-gray-500">${stock.name}</div>
                ${stock.sector === 'Tracked' ? '<div class="text-[9px] text-warren-accent px-1 border border-warren-accent/30 rounded inline-block mt-1">OWNED</div>' : ''}
            </td>
            <td class="px-6 py-4 ${dropColor}">${stock.drop_pct}%</td>
            <td class="px-6 py-4 ${rec5Color}">${stock.recovery_5d || 0}%</td>
            <td class="px-6 py-4 ${rec15Color}">${stock.recovery_15d || 0}%</td>
            <td class="px-6 py-4 ${rsiColor}">${stock.rsi}</td>
            <td class="px-6 py-4 text-gray-300">${stock.roe}%</td>
            <td class="px-6 py-4 text-gray-300">${stock.debt_equity}</td>
            <td class="px-6 py-4">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${badgeColor}">${stock.classification}</span>
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

    const cols = ['ticker', 'drop_pct', 'recovery_5d', 'recovery_15d', 'rsi', 'roe', 'debt_equity', 'classification'];
    cols.forEach(c => {
        const span = document.getElementById(`sort-${c}`);
        if (span) {
            span.textContent = CURRENT_SORT_COL === c ? (CURRENT_SORT_DIR === 'asc' ? '↑' : '↓') : '↕';
            span.style.opacity = CURRENT_SORT_COL === c ? '1' : '0.5';
        }
    });

    renderDipStocks();
}
