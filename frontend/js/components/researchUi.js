import { API_BASE } from '../api.js';
import { renderWithTooltip, renderMetricWithContext, linkTV, formatCurrency } from '../utils.js';
import { MACRO_DATA } from './marketStatus.js';
import { loadTickerSignals } from './tickerSignals.js';

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

let priceChartInstance = null;

export async function loadPriceChart(symbol) {
    const canvas = document.getElementById('price-chart-canvas');
    if (!canvas) return;

    try {
        const res = await fetch(`${API_BASE}/research/price-chart/${encodeURIComponent(symbol)}?days=365`);
        const data = await res.json();
        if (data.error || !data.price_history) return;

        const ph = data.price_history;
        const dates = ph.dates || [];
        const prices = ph.prices || [];
        const sma9 = ph.sma_9 || [];
        const sma50 = ph.sma_50 || [];
        const sma180 = ph.sma_180 || [];

        if (dates.length === 0) return;

        if (priceChartInstance) priceChartInstance.destroy();

        const ctx = canvas.getContext('2d');

        const zoneColors = {
            dip: 'rgba(34, 197, 94, 0.06)',
            institutional: 'rgba(59, 130, 246, 0.06)',
            public: 'rgba(239, 68, 68, 0.06)',
        };

        priceChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [
                    {
                        label: `${symbol} Price`,
                        data: prices,
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.05)',
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        fill: false,
                        order: 1,
                    },
                    {
                        label: 'SMA 9',
                        data: sma9,
                        borderColor: '#60a5fa',
                        borderWidth: 1,
                        pointRadius: 0,
                        borderDash: [4, 4],
                        fill: false,
                        order: 2,
                    },
                    {
                        label: 'SMA 50',
                        data: sma50,
                        borderColor: '#a78bfa',
                        borderWidth: 1,
                        pointRadius: 0,
                        borderDash: [6, 3],
                        fill: false,
                        order: 3,
                    },
                    {
                        label: 'SMA 180',
                        data: sma180,
                        borderColor: '#fb923c',
                        borderWidth: 1,
                        pointRadius: 0,
                        borderDash: [8, 4],
                        fill: false,
                        order: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(17, 24, 39, 0.95)',
                        titleColor: '#9ca3af',
                        bodyColor: '#fff',
                        borderColor: 'rgba(75, 85, 99, 0.3)',
                        borderWidth: 1,
                        padding: 12,
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.raw == null) return null;
                                return `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: '#6b7280',
                            font: { size: 9 },
                            maxTicksLimit: 12,
                            callback: (val, idx) => {
                                const label = dates[idx];
                                if (!label) return '';
                                const parts = label.split('-');
                                return parts.length >= 2 ? `${parts[0]}-${parts[1]}` : label;
                            },
                        },
                    },
                    y: {
                        grid: { color: 'rgba(75, 85, 99, 0.15)' },
                        ticks: {
                            color: '#6b7280',
                            font: { size: 10 },
                            callback: (val) => '$' + val.toFixed(0),
                        },
                    },
                },
            },
            plugins: [{
                id: 'zoneBackgrounds',
                beforeDraw(chart) {
                    const { ctx, chartArea, scales } = chart;
                    if (!chartArea) return;
                    const { left, right, top, bottom } = chartArea;

                    const priceData = chart.data.datasets[0].data;
                    const sma50Data = chart.data.datasets[2].data;
                    const sma180Data = chart.data.datasets[3].data;

                    if (!priceData || priceData.length === 0) return;

                    const xScale = scales.x;
                    const yScale = scales.y;

                    let currentZone = null;
                    let zoneStart = null;

                    for (let i = 0; i < priceData.length; i++) {
                        const price = priceData[i];
                        const s50 = sma50Data[i];
                        const s180 = sma180Data[i];

                        let zone;
                        if (price != null && s180 != null && price < s180) {
                            zone = 'dip';
                        } else if (price != null && s50 != null && price < s50) {
                            zone = 'institutional';
                        } else {
                            zone = 'public';
                        }

                        const xPos = xScale.getPixelForValue(i);

                        if (zone !== currentZone) {
                            if (currentZone && zoneStart !== null) {
                                const xEnd = xPos;
                                ctx.fillStyle = zoneColors[currentZone];
                                ctx.fillRect(zoneStart, top, xEnd - zoneStart, bottom - top);
                            }
                            currentZone = zone;
                            zoneStart = xPos;
                        }
                    }

                    if (currentZone && zoneStart !== null) {
                        ctx.fillStyle = zoneColors[currentZone];
                        ctx.fillRect(zoneStart, top, right - zoneStart, bottom - top);
                    }
                },
            }],
        });
    } catch (err) {
        console.error('Price chart error:', err);
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

        // Update table headers with benchmarks
        setTimeout(() => {
            const table = document.getElementById('sector-stocks-table');
            if (table) {
                const headers = table.querySelectorAll('th');
                if (headers.length >= 6) {
                    headers[2].innerHTML = `P/E <div class="text-[10px] text-gray-500 normal-case font-normal">Avg: ${data.avg_pe || '0.00'}</div>`;
                    headers[3].innerHTML = `ROE % <div class="text-[10px] text-gray-500 normal-case font-normal">Avg: ${data.avg_roe || '0.00'}</div>`;
                    headers[4].innerHTML = `Debt/Eq <div class="text-[10px] text-gray-500 normal-case font-normal">Avg: ${data.avg_debt_equity || '0.00'}</div>`;
                    headers[5].innerHTML = `Margin % <div class="text-[10px] text-gray-500 normal-case font-normal">Avg: ${data.avg_profit_margin || '0.00'}</div>`;
                }
            }
        }, 100);

        data.all_analyzed.forEach(stock => {
            const isTop = data.top_stocks.find(t => t.symbol === stock.symbol);
            const tr = document.createElement('tr');
            tr.className = isTop ? "bg-warren-accent/5" : "text-gray-400 hover:bg-gray-800/10 transition-colors";
            
            // Comparison indicators
            const peColor = stock.pe < data.avg_pe ? 'text-green-400' : 'text-gray-400';
            const roeColor = stock.roe > data.avg_roe ? 'text-green-400' : 'text-gray-400';
            const deColor = stock.debt_to_equity < data.avg_debt_equity ? 'text-green-400' : 'text-gray-400';
            const marginColor = stock.profit_margin > data.avg_profit_margin ? 'text-green-400' : 'text-gray-400';

            const peIndicator = stock.pe < data.avg_pe ? '<span class="text-[8px] block opacity-60">↑ Value</span>' : '';
            const roeIndicator = stock.roe > data.avg_roe ? '<span class="text-[8px] block opacity-60">↑ Strong</span>' : '';
            const deIndicator = stock.debt_to_equity < data.avg_debt_equity ? '<span class="text-[8px] block opacity-60">↓ Safe</span>' : '';
            const marginIndicator = stock.profit_margin > data.avg_profit_margin ? '<span class="text-[8px] block opacity-60">↑ Efficient</span>' : '';

            tr.innerHTML = `
                <td class="py-3 font-medium ${isTop ? 'text-white' : ''}">${linkTV(stock.symbol)}</td>
                <td class="py-3 font-mono text-gray-300">$${stock.price.toFixed(2)}</td>
                <td class="py-3 font-mono ${peColor}">
                    ${stock.pe}
                    ${peIndicator}
                </td>
                <td class="py-3 font-mono ${roeColor}">
                    ${stock.roe}%
                    ${roeIndicator}
                </td>
                <td class="py-3 font-mono ${deColor}">
                    ${stock.debt_to_equity}
                    ${deIndicator}
                </td>
                <td class="py-3 font-mono ${marginColor}">
                    ${stock.profit_margin}%
                    ${marginIndicator}
                </td>
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

        if (!res.ok) {
            const msg = data.detail || data.error || `Server returned ${res.status}`;
            throw new Error(msg);
        }
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
                            <div class="text-4xl font-black text-white mb-1">
                                $${data.market_data ? (data.market_data.price || 0).toFixed(2) : '0.00'}
                            </div>
                            <div class="text-sm font-bold ${((data.market_data || {}).change_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}">
                                ${((data.market_data || {}).change_pct || 0) >= 0 ? '▲' : '▼'} ${((data.market_data || {}).change_pct || 0).toFixed(2)}% Today
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
                            ${data.technical_indicators && data.technical_indicators.rsi_14 != null ? `
                            <div class="flex justify-between items-center pt-2 border-t border-gray-800/50">
                                <span class="text-xs text-gray-400" title="Relative Strength Index (14-day)">RSI (14)</span>
                                <span class="text-sm font-mono font-bold ${data.technical_indicators.rsi_14 < 30 ? 'text-green-400' : data.technical_indicators.rsi_14 > 70 ? 'text-red-400' : 'text-white'}">
                                    ${data.technical_indicators.rsi_14}
                                    ${data.technical_indicators.rsi_14 < 30 ? '<span class="text-[9px] ml-1 text-green-400">Oversold</span>' : data.technical_indicators.rsi_14 > 70 ? '<span class="text-[9px] ml-1 text-red-400">Overbought</span>' : ''}
                                </span>
                            </div>` : ''}
                        </div>
                    </div>

                    <!-- Ticker Signals -->
                    <div id="research-ticker-signals"></div>

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
            </div>

            <!-- Valuation Laboratory — full width -->
            <div class="glass-panel p-8 rounded-2xl border border-gray-800 mt-6">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
                    <div>
                        <h3 class="text-lg font-black text-white uppercase tracking-widest">Valuation Laboratory</h3>
                        <p class="text-xs text-gray-500 mt-1">Multi-model intrinsic value analysis — comparing 5 independent valuation frameworks</p>
                    </div>
                    <div class="flex items-center gap-3">
                        <div class="text-right">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Consensus Fair Value</div>
                            <div class="text-2xl font-black ${data.consensus_valuation.margin_of_safety >= 0 ? 'text-green-400' : 'text-red-400'}">
                                $${data.consensus_valuation.intrinsic_value.toFixed(2)}
                            </div>
                            <div class="text-[10px] font-bold ${data.consensus_valuation.margin_of_safety >= 0 ? 'text-green-400/70' : 'text-red-400/70'}">
                                ${data.consensus_valuation.margin_of_safety >= 0 ? '↑' : '↓'} ${Math.abs(data.consensus_valuation.margin_of_safety)}% ${data.consensus_valuation.verdict}
                                <span class="text-gray-600 ml-1">(${data.consensus_valuation.models_used} models)</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                    ${(data.valuation_models || []).map(m => {
                        const isUnder = m.margin_of_safety > 0;
                        const isNA = m.intrinsic_value <= 0;
                        const borderColor = isNA ? 'border-gray-800' : isUnder ? 'border-green-500/30' : 'border-red-500/30';
                        const bgGlow = isNA ? '' : isUnder ? 'shadow-green-500/5 shadow-lg' : 'shadow-red-500/5 shadow-lg';
                        const mosColor = isNA ? 'text-gray-600' : isUnder ? 'text-green-400' : 'text-red-400';
                        const methodColors = {
                            'Defensive': 'bg-blue-500/10 text-blue-400',
                            'Intrinsic': 'bg-purple-500/10 text-purple-400',
                            'Buffett': 'bg-amber-500/10 text-amber-400',
                            'Dividend': 'bg-emerald-500/10 text-emerald-400',
                            'Multiples': 'bg-cyan-500/10 text-cyan-400'
                        };
                        const methodClass = methodColors[m.method] || 'bg-gray-500/10 text-gray-400';
                        
                        return `
                            <div class="glass-panel p-5 rounded-2xl border ${borderColor} bg-gray-900/30 ${bgGlow} flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between mb-3">
                                        <span class="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${methodClass}">${m.method}</span>
                                    </div>
                                    <div class="text-sm font-bold text-white mb-1">${m.name}</div>
                                    <div class="text-[10px] text-gray-600 mb-4 leading-relaxed">${m.formula}</div>
                                </div>
                                <div>
                                    <div class="text-2xl font-black text-white mb-1">
                                        ${isNA ? '<span class=\"text-gray-600 text-lg\">N/A</span>' : '$' + m.intrinsic_value.toFixed(2)}
                                    </div>
                                    <div class="text-xs font-bold ${mosColor}">
                                        ${isNA ? m.verdict : (isUnder ? '↑ ' : '↓ ') + Math.abs(m.margin_of_safety) + '% ' + m.verdict}
                                    </div>
                                    <div class="mt-3 pt-3 border-t border-gray-800/50 space-y-1">
                                        ${Object.entries(m.inputs).map(([k, v]) => 
                                            '<div class=\"flex justify-between text-[10px]\"><span class=\"text-gray-600\">' + k + '</span><span class=\"text-gray-400 font-mono\">' + v + '</span></div>'
                                        ).join('')}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>

                <!-- Price vs Fair Value Bar -->
                <div class="mt-6 p-4 bg-gray-900/50 rounded-xl border border-gray-800/50">
                    <div class="flex justify-between text-[10px] text-gray-500 uppercase tracking-widest font-bold mb-2">
                        <span>Current Price: $${(data.market_data.price || 0).toFixed(2)}</span>
                        <span>Consensus IV: $${data.consensus_valuation.intrinsic_value.toFixed(2)}</span>
                    </div>
                    <div class="relative h-3 bg-gray-800 rounded-full overflow-hidden">
                        ${(() => {
                            const p = data.market_data.price || 0;
                            const iv = data.consensus_valuation.intrinsic_value || 1;
                            const ratio = Math.min(p / iv, 2) * 50; // 50% = fair value
                            const barColor = p < iv ? 'bg-green-500' : 'bg-red-500';
                            return '<div class=\"h-full ' + barColor + ' rounded-full transition-all\" style=\"width:' + ratio + '%\"></div>';
                        })()}
                    </div>
                    <div class="flex justify-between text-[9px] text-gray-600 mt-1">
                        <span>Deep Value</span>
                        <span>Fair Value</span>
                        <span>Overpriced</span>
                    </div>
                </div>
            </div>

            <!-- Technical Analysis — SMA Trendlines + Zones -->
            <div class="glass-panel p-8 rounded-2xl border border-gray-800 mt-6">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
                    <div>
                        <h3 class="text-lg font-black text-white uppercase tracking-widest">Technical Analysis</h3>
                        <p class="text-xs text-gray-500 mt-1">Price chart with SMA trendlines and recommendation zones</p>
                    </div>
                    <div class="flex items-center gap-4 mt-4 md:mt-0">
                        <div class="flex items-center gap-2 text-[10px]">
                            <span class="w-3 h-0.5 rounded bg-blue-400 inline-block"></span><span class="text-gray-400">SMA 9</span>
                            <span class="w-3 h-0.5 rounded bg-purple-400 inline-block ml-2"></span><span class="text-gray-400">SMA 50</span>
                            <span class="w-3 h-0.5 rounded bg-orange-400 inline-block ml-2"></span><span class="text-gray-400">SMA 180</span>
                        </div>
                    </div>
                </div>
                <div id="price-chart-container" style="height: 400px; position: relative;">
                    <canvas id="price-chart-canvas"></canvas>
                </div>
                <div class="grid grid-cols-3 gap-4 mt-4">
                    <div class="p-3 rounded-xl bg-green-900/20 border border-green-500/20">
                        <div class="text-[9px] text-green-400 uppercase tracking-widest font-bold mb-1">DIP Zone</div>
                        <div class="text-[10px] text-gray-400">Price below SMA 180 — early entry</div>
                    </div>
                    <div class="p-3 rounded-xl bg-blue-900/20 border border-blue-500/20">
                        <div class="text-[9px] text-blue-400 uppercase tracking-widest font-bold mb-1">Institutional Zone</div>
                        <div class="text-[10px] text-gray-400">Price between SMA 50 and SMA 180</div>
                    </div>
                    <div class="p-3 rounded-xl bg-red-900/20 border border-red-500/20">
                        <div class="text-[9px] text-red-400 uppercase tracking-widest font-bold mb-1">Public Zone</div>
                        <div class="text-[10px] text-gray-400">Price above SMA 50 — late stage</div>
                    </div>
                </div>
            </div>

            <!-- Historical Trends Dashboard — full width, outside the sidebar grid -->
            <div class="glass-panel p-8 rounded-2xl border border-gray-800 mt-6">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
                    <div>
                        <h3 class="text-lg font-black text-white uppercase tracking-widest">Historical Fundamentals</h3>
                        <p class="text-xs text-gray-500 mt-1">Multi-year trends across PE, Revenue, EPS, Earnings Growth, and Free Cash Flow</p>
                    </div>
                    <div class="flex gap-2 mt-4 md:mt-0 bg-gray-900 p-1.5 rounded-xl border border-gray-800" id="trend-range-selector">
                        <button onclick="window.loadTrends('${data.symbol}', '1y')" class="trend-btn px-4 py-1.5 text-xs font-bold rounded-lg text-gray-400 hover:text-white transition-colors" data-range="1y">1Y</button>
                        <button onclick="window.loadTrends('${data.symbol}', '3y')" class="trend-btn px-4 py-1.5 text-xs font-bold rounded-lg text-gray-400 hover:text-white transition-colors" data-range="3y">3Y</button>
                        <button onclick="window.loadTrends('${data.symbol}', '5y')" class="trend-btn px-4 py-1.5 text-xs font-bold rounded-lg bg-warren-accent text-white transition-colors" data-range="5y">5Y</button>
                        <button onclick="window.loadTrends('${data.symbol}', 'max')" class="trend-btn px-4 py-1.5 text-xs font-bold rounded-lg text-gray-400 hover:text-white transition-colors" data-range="max">MAX</button>
                    </div>
                </div>
                
                <div id="trends-loading" class="py-16 text-center text-warren-accent text-sm tracking-widest font-bold uppercase">Fetching Historical Data...</div>
                <div id="trends-grid" class="hidden">
                    <!-- Top row: 3 charts -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                        <div class="glass-panel p-5 rounded-2xl border border-gray-800/50 bg-gray-900/30 hover:border-gray-700 transition-colors" style="min-height: 280px;">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-bold">P/E Ratio · Valuation</div>
                            <div style="height: 230px;"><canvas id="chart-pe"></canvas></div>
                        </div>
                        <div class="glass-panel p-5 rounded-2xl border border-gray-800/50 bg-gray-900/30 hover:border-gray-700 transition-colors" style="min-height: 280px;">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-bold">Total Revenue</div>
                            <div style="height: 230px;"><canvas id="chart-revenue"></canvas></div>
                        </div>
                        <div class="glass-panel p-5 rounded-2xl border border-gray-800/50 bg-gray-900/30 hover:border-gray-700 transition-colors" style="min-height: 280px;">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-bold">Diluted EPS</div>
                            <div style="height: 230px;"><canvas id="chart-eps"></canvas></div>
                        </div>
                    </div>
                    <!-- Bottom row: 2 charts, wider -->
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div class="glass-panel p-5 rounded-2xl border border-gray-800/50 bg-gray-900/30 hover:border-gray-700 transition-colors" style="min-height: 280px;">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-bold">Earnings Growth % (YoY)</div>
                            <div style="height: 230px;"><canvas id="chart-growth"></canvas></div>
                        </div>
                        <div class="glass-panel p-5 rounded-2xl border border-gray-800/50 bg-gray-900/30 hover:border-gray-700 transition-colors" style="min-height: 280px;">
                            <div class="text-[10px] text-gray-500 uppercase tracking-widest mb-3 font-bold">Free Cash Flow</div>
                            <div style="height: 230px;"><canvas id="chart-fcf"></canvas></div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Automatically load trends for 5y and price chart
        setTimeout(() => window.loadTrends(data.symbol, '5y'), 100);
        setTimeout(() => loadPriceChart(data.symbol), 200);
        setTimeout(() => loadTickerSignals(data.symbol, 'research-ticker-signals'), 300);

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

// Global chart instances for trends
const trendCharts = {};

export async function loadTrends(symbol, range) {
    // Update button states
    document.querySelectorAll('.trend-btn').forEach(btn => {
        if (btn.getAttribute('data-range') === range) {
            btn.className = "trend-btn px-3 py-1 text-xs font-bold rounded bg-warren-accent text-white transition-colors";
        } else {
            btn.className = "trend-btn px-3 py-1 text-xs font-bold rounded text-gray-400 hover:text-white transition-colors";
        }
    });

    const loading = document.getElementById('trends-loading');
    const grid = document.getElementById('trends-grid');
    if (!loading || !grid) return;

    loading.classList.remove('hidden');
    grid.classList.add('hidden');

    try {
        const res = await fetch(`${API_BASE}/research/trends/${encodeURIComponent(symbol)}?range=${range}`);
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);

        loading.classList.add('hidden');
        grid.classList.remove('hidden');

        renderTrendChart('chart-pe', 'P/E Ratio', data.pe_trend, '#38bdf8', false);
        renderTrendChart('chart-revenue', 'Total Revenue', data.revenue_trend, '#22c55e', true);
        renderTrendChart('chart-eps', 'Diluted EPS', data.eps_trend, '#a855f7', false);
        renderTrendChart('chart-growth', 'Earnings Growth %', data.growth_trend, '#f472b6', false, '%');
        renderTrendChart('chart-fcf', 'Free Cash Flow', data.fcf_trend, '#eab308', true);

    } catch (err) {
        console.error("Trends error:", err);
        loading.innerHTML = `<span class="text-red-400">Failed to load historical trends.</span>`;
    }
}

function renderTrendChart(canvasId, label, dataArray, colorCode, isLargeCurrency, unit = '') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (trendCharts[canvasId]) {
        trendCharts[canvasId].destroy();
    }

    if (!dataArray || dataArray.length === 0) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#6b7280';
        ctx.font = '12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText(`Insufficient data for ${label}`, canvas.width / 2, canvas.height / 2);
        return;
    }

    const labels = dataArray.map(d => d.date.includes('Q') ? d.date : d.date.split('-')[0]);
    const values = dataArray.map(d => d.value);

    // Dynamic gradient for a "soothing" look
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, colorCode + '33'); // 20% opacity
    gradient.addColorStop(1, colorCode + '00'); // 0% opacity

    trendCharts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: values,
                borderColor: colorCode,
                backgroundColor: gradient,
                fill: true,
                tension: 0.4, // Smoother curves
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: colorCode,
                pointBorderColor: '#000',
                pointHoverRadius: 6,
                pointHoverBackgroundColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    titleColor: '#9ca3af',
                    bodyColor: '#fff',
                    borderColor: 'rgba(75, 85, 99, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: (ctx) => {
                            let val = ctx.raw;
                            if (isLargeCurrency) {
                                if (Math.abs(val) >= 1e12) val = '$' + (val / 1e12).toFixed(2) + 'T';
                                else if (Math.abs(val) >= 1e9) val = '$' + (val / 1e9).toFixed(2) + 'B';
                                else if (Math.abs(val) >= 1e6) val = '$' + (val / 1e6).toFixed(1) + 'M';
                                else val = '$' + val.toLocaleString();
                            } else {
                                val = val.toLocaleString() + unit;
                            }
                            return `${label}: ${val}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#6b7280', font: { size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(75, 85, 99, 0.1)' },
                    ticks: {
                        color: '#6b7280',
                        font: { size: 10 },
                        callback: (val) => {
                            if (isLargeCurrency) {
                                if (Math.abs(val) >= 1e9) return '$' + (val / 1e9).toFixed(0) + 'B';
                                if (Math.abs(val) >= 1e6) return '$' + (val / 1e6).toFixed(0) + 'M';
                                return '$' + val;
                            }
                            return val + unit;
                        }
                    }
                }
            }
        }
    });
}

