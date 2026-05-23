import { API_BASE } from '../api.js';
import { renderWithTooltip, linkTV, linkDataromaManager } from '../utils.js';

// --- Superinvestor Logic ---
export async function loadSuperinvestors() {
    const container = document.getElementById('superinvestor-container');
    if (!container) return;
    if (container.children.length > 0) return;

    try {
        const res = await fetch(`${API_BASE}/superinvestors`);
        const payload = await res.json();
        const investors = Array.isArray(payload) ? payload : (payload.investors || []);
        const nextFiling = payload.next_filing;
        const filingStatus = payload.filing_status;

        const filingEl = document.getElementById('next-filing-info');
        if (filingEl) {
            filingEl.classList.remove('hidden');
            filingEl.classList.remove('animate-pulse');

            if (filingStatus) {
                filingEl.textContent = filingStatus.badge;
                const colorMap = {
                    'green': 'bg-green-500/10 border-green-500/20 text-green-400',
                    'yellow': 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400',
                    'red': 'bg-red-500/10 border-red-500/20 text-red-400'
                };
                filingEl.className = `inline-block border px-4 py-2 rounded-full text-sm font-medium ${colorMap[filingStatus.badge_color] || colorMap['green']}`;
            } else if (nextFiling) {
                filingEl.textContent = nextFiling.status;
            }
        }

        container.innerHTML = '';

        investors.forEach(investor => {
            const card = document.createElement('div');
            card.className = "glass-panel p-0 rounded-2xl border border-gray-700/50 hover:border-warren-accent/50 transition-all overflow-hidden flex flex-col cursor-pointer";
            card.dataset.investorId = investor.id;
            card.onclick = () => openSuperinvestorDetail(investor.id);

            card.innerHTML = `
                <div class="p-6 bg-gray-800/30 border-b border-gray-700">
                    <div class="flex items-center gap-4 mb-2">
                        <div class="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center text-xl font-bold text-white shadow-inner">
                            ${investor.name.split(' ').map(n => n[0]).join('')}
                        </div>
                        <div>
                            <h3 class="text-xl font-bold text-white">${investor.name}</h3>
                            <div class="text-xs text-gray-400">${investor.firm}</div>
                            <div class="mt-0.5">${linkDataromaManager(investor.dataroma_code)}</div>
                        </div>
                    </div>
                    <div class="mt-2 text-xs text-warren-accent font-medium uppercase tracking-wider">${investor.style}</div>
                </div>
                <div class="p-6 space-y-8 max-h-[500px] overflow-y-auto custom-scrollbar">
                    ${investor.history.map((quarter, idx) => {
                const isLatest = idx === 0;
                const buys = quarter.top_buys.map(b =>
                    `<div class="flex justify-between items-center text-sm mb-1"><span class="text-gray-300 tracking-wide font-medium">${b.name} (${linkTV(b.symbol)})</span> <span class="text-green-400 text-xs bg-green-400/10 px-2 py-0.5 rounded">${b.change}</span></div>`
                ).join('');

                const sells = quarter.top_sells.map(s =>
                    `<div class="flex justify-between items-center text-sm mb-1"><span class="text-gray-400 decoration-line-through">${s.name} (${linkTV(s.symbol)})</span> <span class="text-red-400 text-xs bg-red-400/10 px-2 py-0.5 rounded">${s.change}</span></div>`
                ).join('');

                const weird = quarter.weirdest_bet ? `
                             <div class="bg-gray-800/80 p-3 rounded-lg mt-3 border-l-2 border-purple-500">
                                <div class="flex justify-between items-center mb-1">
                                    <span class="font-bold text-white text-sm">${linkTV(quarter.weirdest_bet.symbol)}</span>
                                    <span class="text-[10px] uppercase text-purple-300 font-bold tracking-wider">${renderWithTooltip(quarter.weirdest_bet.type)}</span>
                                </div>
                                <p class="text-xs text-gray-400 leading-relaxed">"${quarter.weirdest_bet.description}"</p>
                             </div>
                        ` : '';

                return `
                            <div class="relative ${!isLatest ? 'opacity-80 hover:opacity-100 transition-opacity' : ''}">
                                ${!isLatest ? '<div class="absolute -left-3 top-2 bottom-0 w-0.5 bg-gray-700"></div>' : ''}
                                <div class="flex items-center gap-2 mb-3">
                                    <span class="text-sm font-bold ${isLatest ? 'text-white bg-warren-accent/20 px-2 py-1 rounded' : 'text-gray-500'}">${quarter.quarter}</span>
                                    ${isLatest ? '<span class="text-[10px] text-green-400 animate-pulse">● Latest</span>' : ''}
                                </div>
                                <p class="text-sm text-gray-400 italic mb-4">"${quarter.summary}"</p>
                                
                                <div class="space-y-4 pl-2">
                                    <div>
                                        <h4 class="text-[10px] uppercase text-gray-500 font-bold mb-2">Top Moves</h4>
                                        <div class="space-y-1">${buys}</div>
                                        <div class="space-y-1 mt-1">${sells}</div>
                                    </div>
                                    ${weird}
                                </div>
                            </div>
                            ${!isLatest && idx !== investor.history.length - 1 ? '<hr class="border-gray-700/50 my-6">' : ''}
                        `;
            }).join('<hr class="border-gray-700 my-6">')}
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error("Failed to load superinvestors", err);
    }
}

// --- Copycat Portfolio Logic ---
let _copycatCurrentFilter = 'all';

function _badgeColor(investorName) {
    if (investorName.includes('Buffett')) return 'bg-blue-500/20 text-blue-300';
    if (investorName.includes('Burry')) return 'bg-red-500/20 text-red-300';
    if (investorName.includes('Druckenmiller')) return 'bg-yellow-500/20 text-yellow-300';
    if (investorName.includes('Pabrai')) return 'bg-purple-500/20 text-purple-300';
    if (investorName.includes('Gates')) return 'bg-green-500/20 text-green-300';
    if (investorName.includes('Einhorn')) return 'bg-orange-500/20 text-orange-300';
    return 'bg-gray-700 text-gray-300';
}

function _signalBadge(tags) {
    if (!tags || tags.length === 0) return '<span class="text-xs text-gray-500">Held</span>';
    const tagLabels = {
        overlap:   { label: 'Multi-Manager', cls: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
        new_buys:  { label: 'New Buy',       cls: 'bg-green-500/20 text-green-300 border-green-500/30' },
        increased: { label: 'Conviction Up', cls: 'bg-purple-500/20 text-purple-300 border-purple-500/30' },
        decreased: { label: 'Trimmed',       cls: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' },
        exits:     { label: 'Exit',          cls: 'bg-red-500/20 text-red-300 border-red-500/30' },
        held:      { label: 'Held',          cls: 'bg-gray-700/50 text-gray-400 border-gray-600/30' },
    };
    return tags.map(t => {
        const m = tagLabels[t] || { label: t, cls: 'bg-gray-700/50 text-gray-400' };
        return `<span class="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border ${m.cls}">${m.label}</span>`;
    }).join(' ');
}

function _updateCopycatFilterUI(filter) {
    _copycatCurrentFilter = filter;
    document.querySelectorAll('#copycat-filters button').forEach(btn => {
        if (btn.dataset.filter === filter) {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-warren-accent text-white';
        } else {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-gray-800 text-gray-400 hover:text-white';
        }
    });
}

export async function loadCopycatPortfolio(filter) {
    if (!filter) filter = _copycatCurrentFilter;
    _updateCopycatFilterUI(filter);

    const tbody = document.getElementById('copycat-table-body');
    if (!tbody) return;

    const copycatHeader = document.getElementById('copycat-universe-badge');
    if (copycatHeader) copycatHeader.innerHTML = window.renderUniverseBadge(null, 'curated') + ' <span class="text-gray-500 normal-case font-normal text-[10px]">Live from SEC EDGAR 13F filings</span>';

    tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-8 text-center text-gray-500 animate-pulse">Loading copycat data...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/copycat?filter=${filter}`);
        const json = await res.json();

        if (json._error || json.error || !json.data) {
            tbody.innerHTML = `<tr><td colspan="7" class="px-6 py-4 text-center text-red-400">${json._message || json.message || 'Failed to load data.'}</td></tr>`;
            const note = document.getElementById('copycat-source-note');
            if (note) note.textContent = '';
            return;
        }

        const data = json.data;
        tbody.innerHTML = '';

        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-8 text-center text-gray-500">No stocks match this filter.</td></tr>';
        }

        data.forEach(stock => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-800/50 transition-colors";

            const dailyColor = stock.daily_change >= 0 ? 'text-green-400' : 'text-red-400';
            const yearColor = stock.yearly_change >= 0 ? 'text-green-400' : 'text-red-400';
            const dailySign = stock.daily_change > 0 ? '+' : '';
            const yearSign = stock.yearly_change > 0 ? '+' : '';

            const badges = (stock.held_by || []).map(h =>
                `<span class="text-[10px] uppercase font-bold px-2 py-0.5 rounded ${_badgeColor(h)}">${h}</span>`
            ).join(' ');

            tr.innerHTML = `
                <td class="px-6 py-4">
                    <div class="font-bold text-white">${linkTV(stock.symbol)}</div>
                    <div class="text-xs text-gray-500">${stock.name || ''}</div>
                </td>
                <td class="px-6 py-4"><div class="flex flex-wrap gap-1">${badges}</div></td>
                <td class="px-6 py-4"><div class="flex flex-wrap gap-1">${_signalBadge(stock.filter_tags)}</div></td>
                <td class="px-6 py-4 text-right font-mono text-white">${stock.price > 0 ? '$' + stock.price.toFixed(2) : '--'}</td>
                <td class="px-6 py-4 text-right font-mono ${dailyColor}">${stock.daily_change !== 0 ? dailySign + stock.daily_change + '%' : '--'}</td>
                <td class="px-6 py-4 text-right font-mono ${yearColor}">${stock.yearly_change !== 0 ? yearSign + stock.yearly_change + '%' : '--'}</td>
                <td class="px-6 py-4 text-right">
                     <button onclick="window.searchStock('${stock.symbol}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                        Analyze
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

        const note = document.getElementById('copycat-source-note');
        if (note) {
            const src = json.source === 'sec_edgar' ? 'SEC EDGAR' : 'Static fallback';
            note.textContent = `Source: ${src} · ${json.count} holdings · Filter: ${filter}`;
        }
    } catch (err) {
        console.error("Failed to load copycat", err);
        tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-4 text-center text-red-400">Failed to load copycat data.</td></tr>';
    }
}

// --- Moonshot Logic ---
export let MOONSHOT_STOCKS = [];

export async function loadMoonshots() {
    const cols = {
        '3y': document.getElementById('moonshot-col-3y'),
        '5y': document.getElementById('moonshot-col-5y'),
        '10y': document.getElementById('moonshot-col-10y')
    };

    if (!cols['3y'] || MOONSHOT_STOCKS.length > 0) return;

    Object.values(cols).forEach(c => c.innerHTML = '<div class="text-center text-purple-400 animate-pulse text-xs">Scanning Future...</div>');

    try {
        const res = await fetch(`${API_BASE}/moonshots`);
        const data = await res.json();
        MOONSHOT_STOCKS = data;

        const moonHeader = document.getElementById('moonshot-universe-badge');
        if (moonHeader) moonHeader.innerHTML = window.renderUniverseBadge(null, 'curated') + ' <span class="text-gray-500 normal-case font-normal text-[10px]">Thematic picks</span>';

        renderMoonshots(data);
        setupMoonshotFilters();

    } catch (err) {
        console.error("Failed to load moonshots", err);
        Object.values(cols).forEach(c => c.innerHTML = '<div class="text-center text-red-400 text-xs">Signal Lost.</div>');
    }
}

function renderMoonshots(stocks) {
    const cols = {
        '3y': document.getElementById('moonshot-col-3y'),
        '5y': document.getElementById('moonshot-col-5y'),
        '10y': document.getElementById('moonshot-col-10y')
    };

    Object.values(cols).forEach(c => c.innerHTML = '');

    stocks.forEach(stock => {
        const targetCol = cols[stock.horizon];
        if (!targetCol) return;

        const card = document.createElement('div');
        card.className = "bg-gray-900/80 border border-gray-700 p-4 rounded-lg relative overflow-hidden group hover:border-purple-500/50 transition-all";

        const exposureColor = stock.role === 'Direct' ? 'bg-purple-500 text-white' : 'bg-gray-700 text-gray-400';
        const scoreWidth = stock.innovation_score;
        const scoreColor = scoreWidth > 80 ? 'bg-pink-500' : 'bg-blue-500';
        const tickerHtml = stock.symbol ? linkTV(stock.symbol) : '<span class="text-red-500">N/A</span>';
        const discoveryBadge = stock.is_discovery ? `<div class="absolute -right-12 top-4 rotate-45 bg-warren-accent text-[8px] font-black py-1 px-12 shadow-lg z-10">DISCOVERY 🚀</div>` : '';

        card.innerHTML = `
            ${discoveryBadge}
            <div class="absolute top-0 left-0 w-1 h-full ${scoreColor} opacity-50"></div>
            <div class="flex justify-between items-start mb-2 pl-2">
                <div>
                    <h4 class="font-bold text-white text-lg tracking-wide">${tickerHtml}</h4>
                    <div class="text-[10px] text-gray-400 uppercase tracking-wide">${stock.theme}</div>
                </div>
                <span class="text-[10px] uppercase font-bold px-2 py-0.5 rounded ${exposureColor}">${stock.role}</span>
            </div>
            
            <p class="text-xs text-gray-400 mb-3 leading-relaxed pl-2">
                ${stock.description}
            </p>
            
            <div class="flex justify-between items-center text-xs text-gray-500 pl-2">
                <span>$${stock.price}</span>
                <span class="${stock.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}">${stock.change_pct > 0 ? '+' : ''}${stock.change_pct}%</span>
            </div>
            
            <div class="mt-3 pl-2">
                <div class="flex justify-between text-[10px] text-gray-500 mb-1">
                    <span>Innovation Score</span>
                    <span>${stock.innovation_score}/100</span>
                </div>
                <div class="h-1 w-full bg-gray-800 rounded-full overflow-hidden">
                    <div class="h-full ${scoreColor} rounded-full" style="width: ${scoreWidth}%"></div>
                </div>
            </div>
            
            <button onclick="window.searchStock('${stock.symbol}')" class="absolute inset-0 w-full h-full opacity-0 hover:opacity-100 flex items-center justify-center bg-black/60 transition-opacity backdrop-blur-sm">
                <span class="bg-purple-600 text-white px-4 py-2 rounded-full font-bold shadow-[0_0_15px_rgba(168,85,247,0.5)] transform translate-y-4 group-hover:translate-y-0 transition-transform">
                    Analyze Deeply 🚀
                </span>
            </button>
        `;
        targetCol.appendChild(card);
    });
}

// --- Superinvestor Detail Modal ---
export async function openSuperinvestorDetail(investorId) {
    const modal = document.getElementById('superinvestor-detail-modal');
    if (!modal) return;

    modal.classList.remove('hidden');

    // Set placeholder loading state
    document.getElementById('si-detail-name').textContent = 'Loading...';
    document.getElementById('si-detail-firm').textContent = '';
    document.getElementById('si-detail-style').textContent = '';
    document.getElementById('si-detail-quarter').textContent = '--';
    document.getElementById('si-detail-avatar').textContent = investorId.slice(0, 2).toUpperCase();
    document.getElementById('si-stat-value').textContent = '--';
    document.getElementById('si-stat-holdings').textContent = '--';
    document.getElementById('si-stat-concentration').textContent = '--';
    document.getElementById('si-stat-changes').textContent = '--';
    document.getElementById('si-sector-bars').innerHTML = '<div class="text-sm text-gray-500">Loading...</div>';
    document.getElementById('si-changes-grid').innerHTML = '';
    document.getElementById('si-holdings-body').innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">Loading holdings...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/superinvestors/${investorId}`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Failed to load investor detail');
        }
        const data = await res.json();

        // Populate header
        document.getElementById('si-detail-name').textContent = data.name;
        document.getElementById('si-detail-firm').textContent = data.firm || '';
        document.getElementById('si-detail-style').textContent = data.style || '';
        document.getElementById('si-detail-dataroma').innerHTML = linkDataromaManager(data.dataroma_code);
        document.getElementById('si-detail-quarter').textContent = data.quarter || '--';

        const initials = (data.name || investorId).split(' ').map(n => n[0]).join('').slice(0, 2);
        document.getElementById('si-detail-avatar').textContent = initials;

        // Stats
        const stats = data.stats || {};
        const fm = (v) => {
            if (v === undefined || v === null) return '--';
            if (v >= 1000) return '$' + (v / 1000).toFixed(1) + 'B';
            return '$' + v.toFixed(1) + 'M';
        };
        document.getElementById('si-stat-value').textContent = fm(stats.total_value_millions);
        document.getElementById('si-stat-holdings').textContent = stats.holdings_count ?? '--';
        document.getElementById('si-stat-concentration').textContent = stats.top_concentration != null ? stats.top_concentration + '%' : '--';
        document.getElementById('si-stat-changes').textContent = stats.total_changes ?? '--';

        // Source note
        document.getElementById('si-detail-source').textContent = `Source: ${data.source || 'sec_edgar'} · Quarter: ${data.quarter || 'Unknown'}`;

        // Sector breakdown
        const sectorBars = document.getElementById('si-sector-bars');
        const sectors = stats.sector_breakdown || {};
        const sectorKeys = Object.keys(sectors);
        if (sectorKeys.length > 0) {
            sectorBars.innerHTML = '';
            sectorKeys.forEach(sector => {
                const pct = sectors[sector];
                const bar = document.createElement('div');
                bar.className = 'flex items-center gap-3';
                bar.innerHTML = `
                    <span class="text-xs text-gray-300 w-24 shrink-0 truncate">${sector}</span>
                    <div class="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div class="h-full bg-warren-accent rounded-full transition-all" style="width:${pct}%"></div>
                    </div>
                    <span class="text-xs text-gray-400 w-10 text-right shrink-0">${pct}%</span>
                `;
                sectorBars.appendChild(bar);
            });
        } else {
            sectorBars.innerHTML = '<div class="text-sm text-gray-500 italic">No sector data available</div>';
        }

        // Changes grid
        const changesGrid = document.getElementById('si-changes-grid');
        const changes = data.changes || {};
        const changeTypes = [
            { key: 'new', label: 'New Buys', cls: 'border-green-500/30 text-green-400' },
            { key: 'increased', label: 'Conviction Up', cls: 'border-purple-500/30 text-purple-400' },
            { key: 'decreased', label: 'Trimmed', cls: 'border-yellow-500/30 text-yellow-400' },
            { key: 'exits', label: 'Exits', cls: 'border-red-500/30 text-red-400' },
        ];
        changesGrid.innerHTML = '';
        changeTypes.forEach(ct => {
            const items = changes[ct.key] || [];
            const div = document.createElement('div');
            div.className = `bg-gray-800/50 rounded-xl p-3 border ${ct.cls}`;
            div.innerHTML = `
                <div class="text-xs font-bold uppercase tracking-wider mb-2">${ct.label} <span class="text-gray-500 font-normal">(${items.length})</span></div>
                ${items.length > 0 ? items.slice(0, 5).map(item => {
                    const sym = item.symbol || item.ticker || '?';
                    const val = item.curr_value_millions || item.value_millions || 0;
                    return `<div class="flex justify-between items-center text-xs py-0.5">
                        <span class="text-gray-300">${linkTV(sym)}</span>
                        <span class="text-gray-500">${val > 0 ? '$' + val.toFixed(0) + 'M' : ''}</span>
                    </div>`;
                }).join('') : '<div class="text-xs text-gray-500 italic">None</div>'}
                ${items.length > 5 ? `<div class="text-[10px] text-gray-600 mt-1">+${items.length - 5} more</div>` : ''}
            `;
            changesGrid.appendChild(div);
        });

        // Holdings table
        const tbody = document.getElementById('si-holdings-body');
        const holdings = data.holdings || [];
        const totalVal = stats.total_value_millions || 1;
        if (holdings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500 italic">No holdings data</td></tr>';
        } else {
            tbody.innerHTML = '';
            holdings.forEach(h => {
                const ticker = h.ticker || h.symbol || '?';
                const val = h.value_millions || 0;
                const weight = totalVal > 0 ? ((val / totalVal) * 100).toFixed(1) : '0.0';
                const name = h.name || '';
                const change = h.change || h.signal || '';
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-gray-800/30 transition-colors';
                const changeBadge = change ? `<span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${
                    change === 'new' || change === 'NEW' ? 'bg-green-500/20 text-green-300' :
                    change === 'increased' || change === 'INCREASED' ? 'bg-purple-500/20 text-purple-300' :
                    change === 'decreased' || change === 'DECREASED' ? 'bg-yellow-500/20 text-yellow-300' :
                    change === 'exit' || change === 'EXIT' ? 'bg-red-500/20 text-red-300' :
                    'bg-gray-700/50 text-gray-400'
                }">${change}</span>` : '<span class="text-xs text-gray-600">--</span>';
                tr.innerHTML = `
                    <td class="px-4 py-3 font-bold text-white">${linkTV(ticker)}</td>
                    <td class="px-4 py-3 text-gray-400 text-xs max-w-[110px] truncate">${name}</td>
                    <td class="px-4 py-3 text-right font-mono text-white">${val.toFixed(1)}</td>
                    <td class="px-4 py-3 text-right font-mono text-gray-400">${weight}%</td>
                    <td class="px-4 py-3">${changeBadge}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) {
        console.error("Failed to load investor detail", err);
        document.getElementById('si-holdings-body').innerHTML = `<tr><td colspan="5" class="px-4 py-8 text-center text-red-400">${err.message}</td></tr>`;
    }
}

// --- Guru Consensus (Grand Portfolio) ---
export async function loadGuruConsensus(view = 'grand_portfolio') {
    const container = document.getElementById('guru-consensus-content');
    const badge = document.getElementById('guru-consensus-badge');
    if (!container) return;

    // Update active filter button
    document.querySelectorAll('#guru-consensus-filters button').forEach(btn => {
        if (btn.dataset.view === view) {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-warren-accent text-white';
        } else {
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-gray-800 text-gray-400 hover:text-white';
        }
    });

    container.innerHTML = '<div class="text-center py-8 text-gray-500 animate-pulse text-sm">Loading guru consensus...</div>';

    try {
        const res = await fetch(`${API_BASE}/guru-consensus?view=${view}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.error) {
            container.innerHTML = `<div class="text-center py-8 text-red-400 text-sm">${data.error}</div>`;
            return;
        }

        if (badge) {
            if (view === 'consensus_picks') {
                badge.textContent = `${data.total_candidates || 0} candidates → ${(data.consensus || []).length} picks`;
            } else {
                const count = data.holdings_count || 0;
                const sectorCount = data.sector_data ? data.sector_data.length : 0;
                badge.textContent = count ? `${count} stocks` : sectorCount ? `${sectorCount} sectors` : '';
            }
        }

        if (view === 'grand_portfolio_sector') {
            renderGuruSector(container, data);
        } else if (view === 'consensus_picks') {
            renderConsensusPicks(container, data);
        } else {
            renderGuruHoldings(container, data, view);
        }
    } catch (err) {
        container.innerHTML = `<div class="text-center py-8 text-red-400 text-sm">Failed: ${err.message}</div>`;
    }
}

function renderGuruHoldings(container, data, view) {
    const holdings = data.holdings || [];
    if (holdings.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-500 text-sm">No holdings data available.</div>';
        return;
    }

    const isQuarterView = view.startsWith('grand_portfolio_qtr');

    let html = `<div class="overflow-x-auto rounded-lg border border-gray-700">
        <table class="w-full text-sm text-left">
            <thead class="text-xs text-gray-400 uppercase bg-gray-900/50">
                <tr>
                    <th class="px-4 py-3 rounded-l-lg">#</th>
                    <th class="px-4 py-3">Symbol</th>
                    <th class="px-4 py-3">Name</th>
                    <th class="px-4 py-3 text-right">% Port</th>
                    <th class="px-4 py-3 text-center">Owners</th>
                    ${isQuarterView ? '<th class="px-4 py-3 text-center">6mo</th>' : ''}
                    <th class="px-4 py-3 text-right">Reported</th>
                    <th class="px-4 py-3 text-right">Current</th>
                    <th class="px-4 py-3 text-right">52w Low</th>
                    <th class="px-4 py-3 text-right">Above Low</th>
                    <th class="px-4 py-3 text-right rounded-r-lg">52w High</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-800">`;

    holdings.forEach((h, i) => {
        const changeClass = h.above_52w_low_pct && (h.above_52w_low_pct.startsWith('+') || parseFloat(h.above_52w_low_pct) > 0) ? 'text-green-400' :
            h.above_52w_low_pct && h.above_52w_low_pct.startsWith('-') ? 'text-red-400' : '';
        const in6mo = h.in_6mo;
        const sixmoBadge = in6mo ? '<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300">6mo</span>' : '<span class="text-gray-600 text-xs">—</span>';
        html += `<tr class="hover:bg-gray-800/30 transition-colors">
            <td class="px-4 py-2.5 text-gray-500">${i + 1}</td>
            <td class="px-4 py-2.5 font-bold text-white">${linkTV(h.symbol || '?')}</td>
            <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[110px] truncate">${h.name || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono text-white">${h.portfolio_pct || ''}</td>
            <td class="px-4 py-2.5 text-center"><span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/20 text-blue-300">${h.ownership_count || '0'}</span></td>
            ${isQuarterView ? `<td class="px-4 py-2.5 text-center">${sixmoBadge}</td>` : ''}
            <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.reported_price || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono text-white">${h.current_price || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.week_52_low || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono ${changeClass}">${h.above_52w_low_pct || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.week_52_high || ''}</td>
        </tr>`;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

function renderConsensusPicks(container, data) {
    const picks = data.consensus || [];
    if (picks.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-500 text-sm">No consensus data available.</div>';
        return;
    }

    const maxScore = Math.max(...picks.map(p => p.score));

    let html = `<div class="text-sm text-gray-400 mb-4">${data.total_candidates} candidates scored — showing top ${picks.length}</div>
    <div class="overflow-x-auto rounded-lg border border-gray-700">
        <table class="w-full text-sm text-left">
            <thead class="text-xs text-gray-400 uppercase bg-gray-900/50">
                <tr>
                    <th class="px-4 py-3 rounded-l-lg">#</th>
                    <th class="px-4 py-3">Symbol</th>
                    <th class="px-4 py-3">Name</th>
                    <th class="px-4 py-3 text-center">Score</th>
                    <th class="px-4 py-3 text-center">Owners</th>
                    <th class="px-4 py-3 text-center">Net</th>
                    <th class="px-4 py-3 text-center">Signals</th>
                    <th class="px-4 py-3 text-right">% Port</th>
                    <th class="px-4 py-3 text-right rounded-r-lg">Price</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-gray-800">`;

    picks.forEach((p, i) => {
        const pct = maxScore > 0 ? (p.score / maxScore) * 100 : 0;
        const barColor = pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-warren-accent' : pct >= 40 ? 'bg-yellow-500' : 'bg-gray-500';
        const netClass = p.net_managers > 0 ? 'text-green-400' : p.net_managers < 0 ? 'text-red-400' : 'text-gray-500';
        const netLabel = p.net_managers > 0 ? `+${p.net_managers}` : p.net_managers === 0 ? '0' : `${p.net_managers}`;

        const signals = [];
        if (p.sustained_buy) signals.push('<span class="text-[9px] uppercase font-bold px-1 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">Sustained</span>');
        if (p.in_6mo) signals.push('<span class="text-[9px] uppercase font-bold px-1 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">6mo</span>');
        if (p.near_low) signals.push('<span class="text-[9px] uppercase font-bold px-1 py-0.5 rounded bg-yellow-500/20 text-yellow-300 border border-yellow-500/30">Near Low</span>');

        html += `<tr class="hover:bg-gray-800/30 transition-colors">
            <td class="px-4 py-2.5 text-gray-500">${i + 1}</td>
            <td class="px-4 py-2.5 font-bold text-white">${linkTV(p.symbol || '?')}</td>
            <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[100px] truncate">${p.name || ''}</td>
            <td class="px-4 py-2.5">
                <div class="flex items-center gap-2">
                    <span class="font-bold text-sm text-white w-6 text-right">${p.score}</span>
                    <div class="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden max-w-[80px]">
                        <div class="h-full ${barColor} rounded-full transition-all" style="width:${pct}%"></div>
                    </div>
                </div>
            </td>
            <td class="px-4 py-2.5 text-center"><span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-blue-500/20 text-blue-300">${p.ownership_count || '0'}</span></td>
            <td class="px-4 py-2.5 text-center font-mono text-sm font-bold ${netClass}">${netLabel}</td>
            <td class="px-4 py-2.5"><div class="flex flex-wrap gap-1">${signals.join('') || '<span class="text-gray-600 text-xs">—</span>'}</div></td>
            <td class="px-4 py-2.5 text-right font-mono text-gray-400">${p.portfolio_pct || ''}</td>
            <td class="px-4 py-2.5 text-right font-mono text-white">${p.current_price || ''}</td>
        </tr>`;
    });

    html += `</tbody></table></div>`;
    container.innerHTML = html;
}

function renderGuruSector(container, data) {
    const sectors = data.sector_data || [];
    if (sectors.length === 0) {
        container.innerHTML = '<div class="text-center py-8 text-gray-500 text-sm">No sector data available.</div>';
        return;
    }

    const maxVal = Math.max(...sectors.map(s => {
        const v = parseFloat((s.value || '').replace(/[^0-9.]/g, ''));
        return isNaN(v) ? 0 : v;
    }));

    let html = `<div class="grid grid-cols-1 md:grid-cols-2 gap-4">`;
    sectors.forEach(s => {
        const v = parseFloat((s.value || '').replace(/[^0-9.]/g, ''));
        const pct = maxVal > 0 ? Math.max(5, (v / maxVal) * 100) : 5;
        html += `<div class="bg-gray-800/50 rounded-xl p-4 border border-gray-700">
            <div class="flex justify-between items-center mb-2">
                <span class="text-sm font-semibold text-white">${s.sector || ''}</span>
                <span class="text-xs text-gray-400">${s.value || ''}</span>
            </div>
            <div class="h-2.5 bg-gray-700 rounded-full overflow-hidden">
                <div class="h-full bg-warren-accent rounded-full transition-all" style="width:${pct}%"></div>
            </div>
        </div>`;
    });
    html += `</div>`;
    container.innerHTML = html;
}

export function closeSuperinvestorDetail() {
    const modal = document.getElementById('superinvestor-detail-modal');
    if (modal) modal.classList.add('hidden');
}

function setupMoonshotFilters() {
    const buttons = document.querySelectorAll('#moonshot-filters button');
    buttons.forEach(btn => {
        btn.onclick = () => {
            buttons.forEach(b => {
                b.className = "bg-gray-800 text-gray-400 hover:text-white px-3 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer";
            });
            btn.className = "bg-purple-500/20 text-purple-300 border border-purple-500/50 px-3 py-1 rounded-full text-xs font-bold cursor-pointer";

            const theme = btn.getAttribute('data-theme');
            if (!theme) return;

            if (theme === 'all') {
                renderMoonshots(MOONSHOT_STOCKS);
            } else {
                const filtered = MOONSHOT_STOCKS.filter(s => s.theme.includes(theme) || theme === 'all');
                renderMoonshots(filtered);
            }
        }
    });
}
