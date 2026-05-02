import { API_BASE } from '../api.js';
import { renderWithTooltip, renderMetricWithContext, linkTV, formatCurrency } from '../utils.js';
import { MACRO_DATA } from './marketStatus.js';

export async function loadIndustries() {
    try {
        const res = await fetch(`${API_BASE}/industries/top`);
        const payload = await res.json();

        const data = Array.isArray(payload) ? payload : (payload.rankings || []);
        const universeMeta = payload.universe_meta || null;

        const tbody = document.getElementById('industry-table-body');
        tbody.innerHTML = '';

        const industryBadgeEl = document.getElementById('industry-universe-badge');
        if (industryBadgeEl && universeMeta) {
            industryBadgeEl.innerHTML = window.renderUniverseBadge(universeMeta);
        }

        data.forEach((ind, index) => {
            const tr = document.createElement('tr');
            tr.className = "hover:bg-gray-700/50 transition-colors group cursor-pointer";
            tr.onclick = () => window.loadStocks(ind.industry);

            let macroHtml = '<span class="text-gray-600">-</span>';
            if (MACRO_DATA && MACRO_DATA.sector_impacts[ind.industry]) {
                const impact = MACRO_DATA.sector_impacts[ind.industry];
                if (impact.impact === 'Tailwind') {
                    macroHtml = `<div class="flex items-center gap-1 text-green-400 text-xs" title="${impact.reasons.join(', ')}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
                        Tailwind
                    </div>`;
                } else if (impact.impact === 'Headwind') {
                    macroHtml = `<div class="flex items-center gap-1 text-red-400 text-xs" title="${impact.reasons.join(', ')}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"></path></svg>
                        Headwind
                    </div>`;
                } else if (impact.impact === 'Neutral') {
                    macroHtml = '<span class="text-gray-400 text-xs">Neutral</span>';
                }
            }

            tr.innerHTML = `
                <td class="px-6 py-4 font-medium text-white group-hover:text-warren-accent transition-colors">
                    ${ind.industry}
                </td>
                <td class="px-6 py-4 text-gray-400">${ind.etf}</td>
                <td class="px-6 py-4">${macroHtml}</td>
                <td class="px-6 py-4">
                    <span class="${ind.pe < 20 ? 'text-green-400' : 'text-gray-300'}">${ind.pe}</span>
                </td>
                <td class="px-6 py-4 text-gray-300">${ind.dividend_yield}%</td>
                <td class="px-6 py-4 text-right">
                    <button class="text-xs bg-warren-accent/10 text-warren-accent px-3 py-1 rounded hover:bg-warren-accent hover:text-white transition-all">
                        Analyze
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });

    } catch (err) {
        console.error("Failed to load industries", err);
    }
}

export async function loadStocks(industryName) {
    const section = document.getElementById('stock-picks-section');
    const container = document.getElementById('stock-cards-container');
    const title = document.getElementById('selected-industry-name');
    const detailBody = document.getElementById('stock-detail-body');

    section.classList.remove('hidden');
    title.textContent = industryName;
    container.innerHTML = '<div class="col-span-full text-center py-10 text-gray-500 animate-pulse">Scanning Sector Fundamentals...</div>';

    section.scrollIntoView({ behavior: 'smooth' });

    try {
        const res = await fetch(`${API_BASE}/stocks/${encodeURIComponent(industryName)}`);
        const data = await res.json();

        container.innerHTML = '';
        detailBody.innerHTML = '';

        if (data.error) {
            container.innerHTML = `<div class="col-span-full text-center text-red-400 py-4">${data.error}</div>`;
            return;
        }

        data.top_stocks.forEach(stock => {
            const card = document.createElement('div');
            card.className = "glass-panel rounded-xl p-5 border-t-4 border-warren-accent hover:transform hover:-translate-y-1 transition-transform duration-300 relative overflow-hidden";

            const scoreWidth = stock.innovation_score;
            const scoreColor = scoreWidth > 80 ? 'bg-pink-500' : 'bg-blue-500';

            const tickerHtml = stock.symbol ? linkTV(stock.symbol) : '<span class="text-red-500">N/A</span>';

            card.innerHTML = `
                <div class="absolute top-0 left-0 w-1 h-full ${scoreColor} opacity-50"></div>
                <div class="flex justify-between items-start mb-2 pl-2">
                    <div>
                        <h4 class="font-bold text-white text-lg tracking-wide">${tickerHtml}</h4>
                        <div class="text-[10px] text-gray-400 uppercase tracking-wide">${stock.theme}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-mono text-white">$${stock.price}</div>
                    </div>
                </div>
                
                <div class="space-y-1.5 mt-2">
                    ${renderMetricWithContext('P/E Ratio', stock.pe, data.avg_pe)}
                    ${renderMetricWithContext('ROE', stock.roe, data.avg_roe, '%')}
                    ${renderMetricWithContext('Debt/Eq', stock.debt_to_equity, data.avg_debt_equity)}
                </div>
                
                <div class="mt-3 pt-2 border-t border-gray-700/50 text-center">
                    <span class="text-[10px] uppercase tracking-wider text-warren-accent font-semibold flex items-center justify-center gap-1">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        Analyst Approved
                    </span>
                </div>
            `;
            container.appendChild(card);
        });

        data.all_analyzed.forEach(stock => {
            const isTop = data.top_stocks.find(t => t.symbol === stock.symbol);
            const tr = document.createElement('tr');
            tr.className = isTop ? "bg-warren-accent/5" : "text-gray-400";
            tr.innerHTML = `
                <td class="py-2 font-medium ${isTop ? 'text-white' : ''}">${linkTV(stock.symbol)}</td>
                <td class="py-2">$${stock.price}</td>
                <td class="py-2">${stock.pe}</td>
                <td class="py-2 ${stock.roe > 15 ? 'text-green-400' : ''}">${stock.roe}%</td>
                <td class="py-2">${stock.debt_to_equity}</td>
                <td class="py-2">${stock.profit_margin}%</td>
            `;
            detailBody.appendChild(tr);
        });

        renderMoatMatrix(data.all_analyzed);

    } catch (err) {
        console.error("Failed to load stocks", err);
        container.innerHTML = `<div class="col-span-full text-center text-red-500">Error loading stock data.</div>`;
    }
}

export async function searchStock(symbol) {
    if (!symbol) return;

    const input = document.getElementById('stock-search');
    const strategySelect = document.getElementById('analyst-select');
    const strategyName = strategySelect.options[strategySelect.selectedIndex].text;
    const strategyValue = strategySelect.value;

    const brandName = strategyName.split(' ')[0] + (strategyValue === 'buffett' ? ' Indicator' : ' Analytics');
    const headerTitle = document.querySelector('header h1');
    if (headerTitle) {
        headerTitle.innerHTML = `${strategyName.split(' ')[0]} <span class="text-warren-accent">${strategyValue === 'buffett' ? 'Indicator' : 'Analytics'}</span>`;
    }

    const originalText = input.placeholder;
    input.disabled = true;
    input.value = `Asking ${strategyName}...`;

    try {
        const res = await fetch(`${API_BASE}/analyze/${encodeURIComponent(symbol)}?strategy=${strategyValue}`);
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            input.value = "";
            input.disabled = false;
            return;
        }

        const tickerSpan = document.getElementById('modal-ticker');
        const tvLink = document.getElementById('modal-tradingview-link');

        if (tickerSpan) {
            tickerSpan.textContent = data.symbol;
        }

        if (tvLink) {
            const cleanSymbol = data.symbol.split(' ')[0].replace(/[^a-zA-Z]/g, '');
            tvLink.href = `https://www.tradingview.com/symbols/${cleanSymbol}/`;
        }

        document.getElementById('modal-name').textContent = data.name;

        const verdictHeader = document.getElementById('modal-verdict-header');
        if (verdictHeader) {
            verdictHeader.textContent = `${strategyName.split(' ')[0]}'s Verdict`;
        }

        const ratingEl = document.getElementById('modal-rating');
        ratingEl.textContent = data.rating;
        ratingEl.className = "text-xl font-bold";

        if (data.rating.includes('BUY') || data.rating.includes('Long')) ratingEl.classList.add('text-warren-success');
        else if (data.rating.includes('HOLD') || data.rating.includes('WATCH') || data.rating.includes('Pass')) ratingEl.classList.add('text-warren-warning');
        else ratingEl.classList.add('text-warren-danger');

        const metricsContainer = document.querySelector('#forecast-modal .grid.grid-cols-2');
        metricsContainer.innerHTML = '';

        const addCard = (label, value, colorClass = 'text-white') => {
            const el = document.createElement('div');
            el.className = 'bg-gray-800/50 p-4 rounded-xl text-center overflow-visible';
            el.innerHTML = `
                <div class="text-xs text-gray-400 uppercase tracking-widest mb-1">${renderWithTooltip(label)}</div>
                <div class="text-2xl font-mono ${colorClass}">${value}</div>
            `;
            metricsContainer.appendChild(el);
        };

        if (strategyValue === 'buffett') {
            const iv = data.intrinsic_value ? formatCurrency(data.intrinsic_value).replace('B', '').replace('T', '') : 'N/A';
            addCard('Intrinsic Value', iv);
            const target = data.target_price_5yr ? formatCurrency(data.target_price_5yr).replace('B', '').replace('T', '') : 'N/A';
            addCard('5-Year Target', target, 'text-warren-accent');

            if (data.implied_growth_rate !== undefined) {
                const ig = data.implied_growth_rate;
                const igColor = ig > 15 ? 'text-warren-danger' : (ig < 5 ? 'text-warren-success' : 'text-yellow-400');
                addCard('Implied Growth', `${ig}%`, igColor);
            }

        } else if (strategyValue === 'lynch') {
            const peg = data.metrics && data.metrics.peg_ratio ? data.metrics.peg_ratio : 'N/A';
            addCard('PEG Ratio', peg, peg < 1.0 ? 'text-warren-success' : 'text-warren-warning');
            const growth = data.projected_growth_rate ? data.projected_growth_rate + '%' : 'N/A';
            addCard('Proj. Growth', growth, 'text-warren-accent');
        } else if (strategyValue === 'burry') {
            const evEbitda = data.metrics && data.metrics.ev_ebitda ? data.metrics.ev_ebitda : 'N/A';
            addCard('EV / EBITDA', evEbitda);
            const distress = data.metrics && data.metrics.debt_to_equity ? data.metrics.debt_to_equity : 'N/A';
            addCard('Debt/Equity', distress, parseFloat(distress) > 2 ? 'text-warren-danger' : 'text-white');
        }

        const chartContainer = document.getElementById('stock-price-chart').parentElement;
        if (data.target_price_5yr && data.target_price_5yr > 0) {
            chartContainer.classList.remove('hidden');
            setTimeout(() => {
                renderGrowthChart(data.symbol, data.current_price, data.target_price_5yr, strategyName);
            }, 100);
        } else {
            chartContainer.classList.add('hidden');
        }

        const reasonsList = document.getElementById('modal-reasons');
        reasonsList.innerHTML = '';
        data.reasons.forEach(r => {
            const li = document.createElement('li');
            li.className = "flex items-start gap-2";
            li.innerHTML = `<span class="text-warren-accent mt-1">•</span> <span>${r}</span>`;
            reasonsList.appendChild(li);
        });

        const footerRow = document.querySelector('#forecast-modal .border-t.flex');
        footerRow.innerHTML = '';

        const addFooterItem = (label, val, color) => {
            const div = document.createElement('span');
            div.innerHTML = `${renderWithTooltip(label)}: <span class="${color || 'text-white'} ml-1">${val}</span>`;
            footerRow.appendChild(div);
        }

        const m = data.metrics || {};

        if (strategyValue === 'buffett') {
            addFooterItem('Est. Growth', data.projected_growth_rate ? `${data.projected_growth_rate}%` : '--', 'text-white');
            addFooterItem('ROE', m.roe ? `${m.roe}%` : '--', m.roe > 15 ? 'text-green-400' : 'text-white');
            addFooterItem('Debt/Eq', m.debt_to_equity || '--', 'text-white');
        } else if (strategyValue === 'lynch') {
            addFooterItem('PEG', m.peg_ratio || '--', m.peg_ratio < 1 ? 'text-green-400' : 'text-white');
            addFooterItem('Div Yield', m.dividend_yield ? `${m.dividend_yield}%` : '0%', 'text-white');
            addFooterItem('Debt/Eq', m.debt_to_equity || '--', 'text-white');
        } else if (strategyValue === 'burry') {
            addFooterItem('EV/EBITDA', m.ev_ebitda || '--', 'text-white');
            addFooterItem('Free Cash Flow', m.fcf_yield ? `${m.fcf_yield}%` : '--', 'text-blue-400');
            addFooterItem('Short Interest', m.short_float ? `${m.short_float}%` : '--', 'text-red-400');
        }

        document.getElementById('forecast-modal').classList.remove('hidden');

    } catch (err) {
        console.error("Analysis failed", err);
        alert("Failed to analyze stock.");
    } finally {
        input.value = "";
        input.placeholder = originalText;
        input.disabled = false;
    }
}

export function renderGrowthChart(symbol, current, target, analystName) {
    const ctx = document.getElementById('stock-price-chart').getContext('2d');

    if (window.myStockChart) {
        window.myStockChart.destroy();
    }

    const labels = ['Now', 'Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5'];
    const growth = (target - current) / 5;
    const dataPoints = Array.from({ length: 6 }, (_, i) => current + (growth * i));

    const isPositive = target > current;
    const color = isPositive ? '#38bdf8' : '#ef4444';
    const bg = isPositive ? 'rgba(56, 189, 248, 0.1)' : 'rgba(239, 68, 68, 0.1)';

    window.myStockChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `${symbol} ${analystName.split(' ')[0]} Projection`,
                data: dataPoints,
                borderColor: color,
                backgroundColor: bg,
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true, labels: { color: '#9ca3af' } },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return '$' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(75, 85, 99, 0.2)' },
                    ticks: { color: '#9ca3af', callback: (val) => '$' + val }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#9ca3af' }
                }
            }
        }
    });
}

export function renderMoatMatrix(stocks) {
    const canvas = document.getElementById('moat-matrix-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    if (window.myMoatChart) {
        window.myMoatChart.destroy();
    }

    const dataPoints = stocks.map(s => ({
        x: s.profit_margin,
        y: s.roe,
        stock: s
    }));

    window.myMoatChart = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Sector Stocks',
                data: dataPoints,
                backgroundColor: (ctx) => {
                    const v = ctx.raw;
                    if (!v) return 'rgba(156, 163, 175, 0.5)';
                    if (v.y > 15 && v.x > 15) return 'rgba(34, 197, 94, 0.8)';
                    if (v.y < 5 || v.x < 5) return 'rgba(239, 68, 68, 0.8)';
                    return 'rgba(56, 189, 248, 0.6)';
                },
                borderColor: 'rgba(255,255,255,0.1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const p = ctx.raw;
                            return `${p.stock.symbol}: ROE ${p.y}% | Margin ${p.x}%`;
                        }
                    }
                },
                legend: { display: false }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Profit Margin (%)', color: '#9ca3af' },
                    grid: { color: 'rgba(75, 85, 99, 0.2)' },
                    ticks: { color: '#9ca3af' }
                },
                y: {
                    title: { display: true, text: 'Return on Equity (ROE %)', color: '#9ca3af' },
                    grid: { color: 'rgba(75, 85, 99, 0.2)' },
                    ticks: { color: '#9ca3af' }
                }
            }
        }
    });
}

export async function startResearch() {
    const input = document.getElementById('research-ticker-input');
    const symbol = input.value.trim().toUpperCase();
    if (!symbol) return;

    await loadResearch(symbol);
}

export const renderWithRating = (label, rating, score) => {
    let color = 'text-gray-400';
    if (rating.includes('BUY')) color = 'text-green-400';
    if (rating.includes('SELL') || rating.includes('SHORT')) color = 'text-red-400';

    return `
        <div class="glass-panel p-4 rounded-xl border border-gray-700/50">
            <div class="text-[10px] uppercase font-bold text-gray-500 mb-2">${label}</div>
            <div class="text-lg font-black ${color}">${rating}</div>
            <div class="text-[10px] text-gray-500 mt-1">Score: <span class="text-white">${score}/10</span></div>
        </div>
    `;
};

export async function loadResearch(symbol) {
    const content = document.getElementById('research-content');
    const empty = document.getElementById('research-empty');
    if (!content || !empty) return;

    content.classList.remove('hidden');
    empty.classList.add('hidden');

    content.innerHTML = `<div class="py-20 text-center animate-pulse text-warren-accent font-black tracking-widest text-xl uppercase">Initiating Institutional Deep Dive for $${symbol}...</div>`;

    try {
        const res = await fetch(`${API_BASE}/research/${symbol}`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        content.innerHTML = `
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Left: Profile & Analysts -->
                <div class="lg:col-span-2 space-y-6">
                    <!-- Identity Card -->
                    <div class="glass-panel p-8 rounded-2xl flex flex-col md:flex-row justify-between items-start gap-6 border-l-4 border-warren-accent">
                        <div>
                            <div class="flex items-center gap-3 mb-2">
                                <h1 class="text-4xl font-black text-white">$${data.symbol}</h1>
                                <span class="px-3 py-1 bg-warren-accent/10 border border-warren-accent/20 rounded-full text-[10px] font-bold text-warren-accent uppercase tracking-widest">${data.sector}</span>
                            </div>
                            <h2 class="text-xl font-bold text-gray-400">${data.name}</h2>
                            <p class="text-xs text-gray-500 mt-4 leading-relaxed max-w-2xl">${(data.summary || '').substring(0, 300)}${(data.summary || '').length > 300 ? '...' : ''}</p>
                        </div>
                        <div class="text-right">
                            <div class="text-4xl font-black text-white mb-1">$${(data.market_data.price || 0).toFixed(2)}</div>
                            <div class="text-sm font-bold ${(data.market_data.change_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}">
                                ${(data.market_data.change_pct || 0) >= 0 ? '▲' : '▼'} ${(data.market_data.change_pct || 0).toFixed(2)}% Today
                            </div>
                            <div class="mt-4 flex gap-2 justify-end">
                                ${linkTV(data.symbol, 'Technical Chart')}
                            </div>
                        </div>
                    </div>

                    <!-- Analyst Consensus -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        ${renderWithRating('Buffett (Quality)', data.analysts.buffett.rating, data.analysts.buffett.score)}
                        ${renderWithRating('Burry (Value)', data.analysts.burry.rating, data.analysts.burry.score)}
                        ${renderWithRating('Lynch (Growth)', data.analysts.lynch.rating, data.analysts.lynch.score)}
                    </div>

                    <!-- Deep Logic Table -->
                    <div class="glass-panel p-6 rounded-2xl">
                        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-6 opacity-60">Strategic Reasoning</h3>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                            <div>
                                <div class="text-[10px] font-black text-warren-accent mb-3 uppercase">Buffett Logic</div>
                                <ul class="space-y-2">
                                    ${(data.analysts.buffett.verdict || []).map(v => `<li class="text-[11px] text-gray-400 flex gap-2"><span>•</span> ${v}</li>`).join('')}
                                </ul>
                            </div>
                            <div>
                                <div class="text-[10px] font-black text-warren-accent mb-3 uppercase">Burry Logic</div>
                                <ul class="space-y-2">
                                    ${(data.analysts.burry.verdict || []).map(v => `<li class="text-[11px] text-gray-400 flex gap-2"><span>•</span> ${v}</li>`).join('')}
                                </ul>
                            </div>
                            <div>
                                <div class="text-[10px] font-black text-warren-accent mb-3 uppercase">Lynch Logic</div>
                                <ul class="space-y-2">
                                    ${(data.analysts.lynch.verdict || []).map(v => `<li class="text-[11px] text-gray-400 flex gap-2"><span>•</span> ${v}</li>`).join('')}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Right: Scorecard & Efficiency -->
                <div class="space-y-6">
                    <!-- Moat Card -->
                    <div class="glass-panel p-6 rounded-2xl bg-gradient-to-br from-gray-900 to-blue-900/20 border border-warren-accent/30 shadow-2xl shadow-blue-500/5">
                        <div class="flex justify-between items-center mb-6">
                            <h3 class="text-sm font-black text-white uppercase tracking-widest">Moat Intelligence</h3>
                            <div class="text-[10px] font-black text-warren-accent ring-1 ring-warren-accent/50 px-2 py-0.5 rounded-full">${data.moat.rating}</div>
                        </div>
                        <div class="flex items-center gap-6 mb-6">
                            <div class="relative w-20 h-20 flex items-center justify-center">
                                <svg class="w-full h-full transform -rotate-90">
                                    <circle cx="40" cy="40" r="32" stroke="currentColor" stroke-width="6" fill="transparent" class="text-gray-800" />
                                    <circle cx="40" cy="40" r="32" stroke="currentColor" stroke-width="6" fill="transparent" class="text-warren-accent" stroke-dasharray="${2 * Math.PI * 32}" stroke-dashoffset="${(1 - data.moat.score / 100) * 2 * Math.PI * 32}" stroke-linecap="round" />
                                </svg>
                                <span class="absolute text-xl font-black text-white">${data.moat.score}</span>
                            </div>
                            <div class="flex-1 space-y-2">
                                ${data.moat.reasons.map(r => `<div class="text-[10px] text-gray-400 leading-tight">• ${r}</div>`).join('')}
                            </div>
                        </div>
                    </div>

                    <!-- Fundamental Grid -->
                    <div class="glass-panel p-6 rounded-2xl space-y-4">
                        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-2 opacity-60">Scorecard</h3>
                        <div class="space-y-3">
                            ${renderMetricWithContext('ROE', (data.quality_scorecard.roe || 0).toFixed(1), 15.0, '%')}
                            ${renderMetricWithContext('P/E Ratio', (data.valuation_scorecard.trailing_pe || 0).toFixed(1), 22.0)}
                            ${renderMetricWithContext('Price / Sales', (data.valuation_scorecard.ps || 0).toFixed(2), 2.0)}
                            ${renderMetricWithContext('FCF Yield', (data.valuation_scorecard.fcf_yield || 0).toFixed(1), 5.0, '%')}
                            ${renderMetricWithContext('Debt / Equity', (data.quality_scorecard.debt_to_equity || 0).toFixed(1), 100.0)}
                        </div>
                    </div>

                    <!-- Growth Reality Check -->
                    <div class="glass-panel p-6 rounded-2xl bg-gray-900 border border-gray-800">
                        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-4">The Reality Check</h3>
                        <div class="space-y-4">
                            <div class="flex justify-between items-center text-xs">
                                <span class="text-gray-500">Market Implied Growth (Perpetual)</span>
                                <span class="text-white font-mono font-bold">${data.growth.implied_growth}%</span>
                            </div>
                            <div class="w-full h-1 bg-gray-800 rounded-full overflow-hidden">
                                <div class="h-full bg-red-400" style="width: ${Math.min(data.growth.implied_growth * 5, 100)}%"></div>
                            </div>
                            <div class="flex justify-between items-center text-xs">
                                <span class="text-gray-500">Buffett Conservative Projection</span>
                                <span class="text-warren-accent font-mono font-bold">${data.growth.projected_5yr}%</span>
                            </div>
                            <div class="w-full h-1 bg-gray-800 rounded-full overflow-hidden">
                                <div class="h-full bg-warren-accent" style="width: ${Math.min(data.growth.projected_5yr * 5, 100)}%"></div>
                            </div>
                            <div class="mt-4 p-3 bg-warren-accent/5 rounded-lg border border-warren-accent/10">
                                <p class="text-[10px] text-gray-400 italic leading-relaxed">
                                    ${data.growth.implied_growth > data.growth.projected_5yr
                ? "⚠️ WARNING: Market pricing in growth far above conservative norms. High risk of disappointment."
                : "✅ CONFIDENCE: Market growth expectations are conservative compared to underlying business metrics."}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

    } catch (err) {
        console.error("Research Hub Error:", err);
        content.innerHTML = `
            <div class="py-20 text-center">
                <div class="text-red-400 text-4xl mb-4">⚠️</div>
                <h3 class="text-xl font-bold text-white">Analysis Interrupted</h3>
                <p class="text-gray-500 mt-2">${err.message || 'Check connection or ticker symbol validity.'}</p>
                <button onclick="window.startResearch()" class="mt-6 px-6 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-700">Retry Analysis</button>
            </div>
        `;
    }
}
