import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';
import { MACRO_DATA } from './marketStatus.js';

export async function loadEconomicIndicators() {
    const grid = document.getElementById('indicators-grid');
    const source = document.getElementById('economics-source');

    if (!grid) return;
    grid.innerHTML = '<div class="col-span-full text-center text-warren-accent">Loading indicators...</div>';

    try {
        const res = await fetch(`${API_BASE}/economic-indicators`);
        const data = await res.json();

        source.textContent = `Source: ${data.source} | Last Updated: ${new Date(data.last_updated).toLocaleString()}`;

        const indicators = data.indicators;
        const labels = {
            'unemployment': { name: 'Unemployment Rate', unit: '%', goodTrend: 'down' },
            'inflation': { name: 'Inflation (CPI)', unit: '%', goodTrend: 'down' },
            'fed_rate': { name: 'Fed Funds Rate', unit: '%', goodTrend: 'stable' },
            'gdp_growth': { name: 'GDP Growth', unit: '%', goodTrend: 'up' }
        };

        grid.innerHTML = '';

        Object.keys(indicators).forEach(key => {
            const indicator = indicators[key];
            const label = labels[key];
            const monthChangeClass = indicator.month_change >= 0 ? 'text-red-400' : 'text-green-400';
            const trendIcon = indicator.trend;

            const card = document.createElement('div');
            card.className = 'glass-panel p-6 rounded-xl';
            card.innerHTML = `
                <div class="text-xs text-gray-400 uppercase tracking-wide mb-2">${label.name}</div>
                <div class="flex items-end justify-between">
                    <div>
                        <div class="text-3xl font-bold text-white">${indicator.value}${label.unit}</div>
                        <div class="${monthChangeClass} text-sm mt-1">
                            ${indicator.month_change > 0 ? '+' : ''}${indicator.month_change}${label.unit} (1M)
                        </div>
                    </div>
                    <div class="text-4xl opacity-50">${trendIcon}</div>
                </div>
                <div class="mt-3 text-xs text-gray-500">
                    YoY: ${indicator.year_change > 0 ? '+' : ''}${indicator.year_change}${label.unit}
                </div>
            `;
            grid.appendChild(card);
        });

    } catch (err) {
        console.error('Failed to load economic indicators', err);
        grid.innerHTML = '<div class="col-span-full text-center text-red-400">Failed to load indicators</div>';
    }
}

export async function loadMoneyFlow() {
    const container = document.getElementById('money-flow-container');
    const summaryContainer = document.getElementById('money-flow-summary');
    const notesContainer = document.getElementById('money-flow-notes');
    const notesList = document.getElementById('money-flow-notes-list');

    if (!container) return;

    container.innerHTML = '<div class="col-span-full text-center text-blue-400 animate-pulse py-10">Analyzing institutional volume & Chaikin Money Flow...</div>';

    try {
        const res = await fetch(`${API_BASE}/money-flow`);
        const data = await res.json();

        if (summaryContainer && data.data.length > 0) {
            summaryContainer.classList.remove('hidden');
            const bestBets = data.data.filter(d => d.score >= 70).slice(0, 2);

            summaryContainer.innerHTML = `
                <div class="glass-panel p-5 rounded-xl border border-green-500/30 bg-green-500/5">
                    <div class="text-xs font-bold text-green-400 uppercase mb-2">🚀 Institutional Conviction: High</div>
                    <div class="text-sm text-gray-300">
                        Institutional accumulation is strongest in <span class="text-white font-bold">${bestBets.length > 0 ? bestBets.map(b => b.symbol).join(' and ') : 'N/A'}</span>. 
                        High relative volume combined with positive Chaikin Money Flow suggests significant position building.
                    </div>
                </div>
                <div class="glass-panel p-5 rounded-xl border border-blue-500/30">
                    <div class="text-xs font-bold text-blue-400 uppercase mb-2">📊 Current Environment</div>
                    <div class="text-sm text-gray-300">
                        Market sentiment is currently ${data.data[0].score > 60 ? 'Bullish' : (data.data[0].score < 40 ? 'Bearish' : 'Mixed')}. 
                        Focus on sectors showing > 1.2x RVOL for high-probability setups.
                    </div>
                </div>
            `;
        }

        if (notesContainer && data.notes) {
            notesContainer.classList.remove('hidden');
            notesList.innerHTML = data.notes.map(note => `<li>${note}</li>`).join('');
        }

        container.innerHTML = '';

        data.data.forEach(item => {
            const card = document.createElement('div');
            card.className = 'glass-panel p-4 rounded-xl border-l-4 transition-all hover:bg-gray-800/50 flex flex-col justify-between h-full';

            const colorClass = item.status_color === 'green' ? 'border-green-500' : (item.status_color === 'red' ? 'border-red-500' : 'border-gray-600');
            const textColor = item.status_color === 'green' ? 'text-green-400' : (item.status_color === 'red' ? 'text-red-400' : 'text-gray-400');
            const bgBadge = item.status_color === 'green' ? 'bg-green-500/10' : (item.status_color === 'red' ? 'bg-red-500/10' : 'bg-gray-500/10');

            card.classList.add(colorClass);

            card.innerHTML = `
                <div>
                    <div class="flex justify-between items-start mb-1">
                        <div>
                            <div class="font-bold text-white text-lg">${linkTV(item.symbol)}</div>
                            <div class="text-[10px] text-warren-accent font-bold uppercase">${item.name}</div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm font-mono text-white">$${item.price}</div>
                            <div class="text-[10px] ${item.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}">${item.change_pct > 0 ? '+' : ''}${item.change_pct}%</div>
                        </div>
                    </div>
                    
                    <p class="text-[10px] text-gray-500 leading-relaxed mb-4 italic">
                        ${item.description}
                    </p>
                    
                    <div class="flex justify-between items-center mb-4">
                        <span class="text-[10px] uppercase font-bold px-2 py-0.5 rounded ${bgBadge} ${textColor}">${item.sentiment}</span>
                        <div class="text-[10px] text-gray-400">RVOL: <span class="text-white font-mono">${item.volume_ratio}x</span></div>
                    </div>
                </div>

                <div class="mt-auto pt-2">
                    <div class="flex justify-between text-[9px] text-gray-500 mb-1">
                        <span>Analysis Conviction</span>
                        <span>${item.score}/100</span>
                    </div>
                    <div class="h-1 w-full bg-gray-800 rounded-full overflow-hidden">
                        <div class="h-full ${item.status_color === 'green' ? 'bg-green-500' : (item.status_color === 'red' ? 'bg-red-500' : 'bg-blue-500')}" style="width: ${item.score}%"></div>
                    </div>
                    <div class="mt-2 text-[8px] text-gray-600 text-right">
                        CMF: ${item.cmf || '0.0'}
                    </div>
                </div>
            `;
            container.appendChild(card);
        });

    } catch (err) {
        console.error('Failed to load money flow', err);
        container.innerHTML = '<div class="col-span-full text-center text-red-400">Failed to load money flow data</div>';
    }
}

export async function loadMarketNews() {
    const feed = document.getElementById('news-feed');
    const source = document.getElementById('news-source');

    if (!feed) return;
    feed.innerHTML = '<div class="text-center text-warren-accent">Loading news...</div>';

    try {
        const res = await fetch(`${API_BASE}/news`);
        const data = await res.json();

        source.textContent = `Sources: ${data.sources.join(', ')} | Last Updated: ${new Date(data.last_updated).toLocaleString()}`;

        feed.innerHTML = '';

        data.news.forEach(item => {
            const newsCard = document.createElement('a');
            newsCard.href = item.link;
            newsCard.target = '_blank';
            newsCard.className = 'block glass-panel p-4 rounded-xl hover:border-warren-accent border border-transparent transition-all';
            newsCard.innerHTML = `
                <div class="flex justify-between items-start gap-4">
                    <div class="flex-1">
                        <h3 class="font-bold text-white mb-1 hover:text-warren-accent">${item.title}</h3>
                        ${item.summary ? `<p class="text-xs text-gray-400 line-clamp-2">${item.summary}</p>` : ''}
                    </div>
                    <div class="text-right flex-shrink-0">
                        <div class="text-xs text-gray-500">${item.published}</div>
                        <div class="text-xs text-gray-600 mt-1">${item.source}</div>
                    </div>
                </div>
            `;
            feed.appendChild(newsCard);
        });

    } catch (err) {
        console.error('Failed to load news', err);
        feed.innerHTML = '<div class="text-center text-red-400">Failed to load news</div>';
    }
}

export let CONTRARIAN_DATA = [];

export async function loadContrarianOpportunities() {
    try {
        const response = await fetch('/api/contrarian/opportunities');
        const data = await response.json();

        CONTRARIAN_DATA = data.opportunities || [];

        const totalEl = document.getElementById('total-opportunities');
        if (totalEl) totalEl.textContent = CONTRARIAN_DATA.length;

        const highConvEl = document.getElementById('high-conviction');
        if (highConvEl) highConvEl.textContent = CONTRARIAN_DATA.filter(o => o.score >= 70).length;

        const avgScore = CONTRARIAN_DATA.reduce((sum, o) => sum + o.score, 0) / CONTRARIAN_DATA.length || 0;
        const avgEl = document.getElementById('avg-score');
        if (avgEl) avgEl.textContent = Math.round(avgScore);

        if (MACRO_DATA && MACRO_DATA.indicators && MACRO_DATA.indicators.vix) {
            const vix = parseFloat(MACRO_DATA.indicators.vix.current) || 0;
            const vixEl = document.getElementById('contrarian-vix');
            if (vixEl) vixEl.textContent = vix.toFixed(1);

            let signal = 'Low Fear';
            if (vix > 30) signal = 'Extreme Fear 🚨';
            else if (vix > 25) signal = 'High Fear ⚠️';
            else if (vix > 20) signal = 'Moderate Fear';

            const sigEl = document.getElementById('contrarian-signal');
            if (sigEl) sigEl.textContent = signal;
        }

        window.filterContrarian('all');

    } catch (err) {
        console.error('Failed to load contrarian opportunities', err);
        const tbody = document.getElementById('contrarian-table-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-red-400">Failed to load opportunities</td></tr>';
    }
}

export function filterContrarian(category) {
    const filters = ['all', 'fallen_angels', 'burry_orphans', 'insider_confidence'];
    filters.forEach(f => {
        const btn = document.getElementById(`contrarian-filter-${f}`);
        if (btn) {
            if (f === category) {
                btn.classList.add('bg-warren-accent', 'text-white');
                btn.classList.remove('text-gray-400', 'hover:bg-gray-800');
            } else {
                btn.classList.remove('bg-warren-accent', 'text-white');
                btn.classList.add('text-gray-400', 'hover:bg-gray-800');
            }
        }
    });

    let filtered = CONTRARIAN_DATA;
    if (category !== 'all') {
        filtered = CONTRARIAN_DATA.filter(o => o.signal === category);
    }

    renderContrarianTable(filtered);
}

function renderContrarianTable(opportunities) {
    const tbody = document.getElementById('contrarian-table-body');
    if (!tbody) return;

    if (opportunities.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-gray-500">No opportunities found for this category</td></tr>';
        return;
    }

    tbody.innerHTML = opportunities.slice(0, 20).map((opp, index) => {
        const scoreClass = opp.score >= 75 ? 'text-green-400' : opp.score >= 60 ? 'text-yellow-400' : 'text-gray-400';
        const changeClass = opp.price_change_52w < 0 ? 'text-red-400' : 'text-green-400';
        const changePrefix = opp.price_change_52w > 0 ? '+' : '';

        let signalBadge = '';
        if (opp.signal === 'fallen_angels') signalBadge = '<span class="text-xs bg-orange-500/20 text-orange-400 px-2 py-1 rounded">🔥 Fallen Angel</span>';
        else if (opp.signal === 'burry_orphans') signalBadge = '<span class="text-xs bg-teal-500/20 text-teal-400 px-2 py-1 rounded">🦉 Orphan</span>';
        else if (opp.signal === 'insider_confidence') signalBadge = '<span class="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded">📈 Insider</span>';

        return `
            <tr class="border-b border-gray-800 hover:bg-gray-800/30 transition-colors">
                <td class="py-3 px-2 text-gray-400 text-sm">#${index + 1}</td>
                <td class="py-3 px-2">
                    <div class="font-semibold text-white">${linkTV(opp.symbol)}</div>
                    <div class="text-xs text-gray-500">${opp.name}</div>
                </td>
                <td class="py-3 px-2">
                    <span class="font-bold ${scoreClass}">${opp.score}</span>
                    <span class="text-xs text-gray-500">/100</span>
                </td>
                <td class="py-3 px-2 ${changeClass} font-medium">
                    ${changePrefix}${opp.price_change_52w.toFixed(1)}%
                </td>
                <td class="py-3 px-2 text-sm text-gray-300 max-w-xs truncate">
                    ${opp.reason}
                </td>
                <td class="py-3 px-2">
                    ${signalBadge}
                </td>
            </tr>
        `;
    }).join('');
}
