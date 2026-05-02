import { API_BASE } from '../api.js';
import { renderWithTooltip, linkTV } from '../utils.js';

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

        const filingEl = document.getElementById('next-filing-info');
        if (filingEl && nextFiling) {
            filingEl.textContent = nextFiling.status;
            filingEl.classList.remove('hidden');
        }

        container.innerHTML = '';

        investors.forEach(investor => {
            const card = document.createElement('div');
            card.className = "glass-panel p-0 rounded-2xl border border-gray-700/50 hover:border-warren-accent/50 transition-all overflow-hidden flex flex-col";

            card.innerHTML = `
                <div class="p-6 bg-gray-800/30 border-b border-gray-700">
                    <div class="flex items-center gap-4 mb-2">
                        <div class="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center text-xl font-bold text-white shadow-inner">
                            ${investor.name.split(' ').map(n => n[0]).join('')}
                        </div>
                        <div>
                            <h3 class="text-xl font-bold text-white">${investor.name}</h3>
                            <div class="text-xs text-gray-400">${investor.firm}</div>
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
export async function loadCopycatPortfolio() {
    const tbody = document.getElementById('copycat-table-body');
    if (!tbody || tbody.children.length > 0) return;

    const copycatHeader = document.getElementById('copycat-universe-badge');
    if (copycatHeader) copycatHeader.innerHTML = window.renderUniverseBadge(null, 'curated') + ' <span class="text-gray-500 normal-case font-normal text-[10px]">Based on 13F SEC filings</span>';

    tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-8 text-center text-gray-500 animate-pulse">Fetching Real-Time Prices...</td></tr>';

    try {
        const res = await fetch(`${API_BASE}/copycat`);
        const data = await res.json();
        tbody.innerHTML = '';

        data.forEach(stock => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-800/50 transition-colors";

            const dailyColor = stock.daily_change >= 0 ? 'text-green-400' : 'text-red-400';
            const yearColor = stock.yearly_change >= 0 ? 'text-green-400' : 'text-red-400';
            const dailySign = stock.daily_change > 0 ? '+' : '';
            const yearSign = stock.yearly_change > 0 ? '+' : '';

            const badges = stock.held_by.map(h => {
                let color = 'bg-gray-700 text-gray-300';
                if (h.includes('Buffett')) color = 'bg-blue-500/20 text-blue-300';
                if (h.includes('Burry')) color = 'bg-red-500/20 text-red-300';
                if (h.includes('Druckenmiller')) color = 'bg-yellow-500/20 text-yellow-300';
                if (h.includes('Pabrai')) color = 'bg-purple-500/20 text-purple-300';
                return `<span class="text-[10px] uppercase font-bold px-2 py-0.5 rounded ${color}">${h}</span>`;
            }).join(' ');

            tr.innerHTML = `
                <td class="px-6 py-4">
                    <div class="font-bold text-white">${linkTV(stock.symbol)}</div>
                    <div class="text-xs text-gray-500">${stock.name}</div>
                </td>
                <td class="px-6 py-4">
                    <div class="flex flex-wrap gap-1">${badges}</div>
                </td>
                <td class="px-6 py-4 text-right font-mono text-white">$${stock.price.toFixed(2)}</td>
                <td class="px-6 py-4 text-right font-mono ${dailyColor}">${dailySign}${stock.daily_change}%</td>
                <td class="px-6 py-4 text-right font-mono ${yearColor}">${yearSign}${stock.yearly_change}%</td>
                <td class="px-6 py-4 text-right">
                     <button onclick="window.searchStock('${stock.symbol}')" class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                        Analyze
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Failed to load copycat", err);
        tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-4 text-center text-red-400">Failed to load data.</td></tr>';
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
