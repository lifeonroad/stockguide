
import { API_BASE } from './js/api.js';
import { linkTV } from './js/utils.js';
import { loadTickerSignals } from './js/components/tickerSignals.js';

let currentPortfolioId = null;
let portfolios = [];

const STORAGE_KEY_PORTFOLIO = 'electric_triangulum_selected_portfolio';
let currentRefreshedPositions = []; // Store positions with prices for sorting
let sortState = {
    column: 'value', // default sort
    direction: 'desc'
};

// Auto-categorize based on ticker patterns
function autoCategorize(ticker) {
    const t = ticker.toUpperCase();

    // ETFs - common patterns
    if (t.match(/^(SPY|QQQ|IWM|DIA|VTI|VOO|VT|VEA|VWO|AGG|BND|TLT|GLD|SLV)$/)) return 'ETF';
    if (t.match(/^V[A-Z]{2}$/)) return 'ETF'; // Vanguard ETFs (VFV, VTV, etc.)
    if (t.match(/^[XZ][A-Z]{2}$/)) return 'ETF'; // iShares Canada (XQQ, ZSP, etc.)
    if (t.match(/^(SCHD|SPHD|JEPI|JEPQ)$/)) return 'ETF'; // Dividend ETFs
    if (t.match(/^(ARKK|ARKG|ARKW|ARKF|ARKQ)$/)) return 'ETF'; // ARK ETFs
    if (t.match(/^(QQQM|QQEW)$/)) return 'ETF'; // Nasdaq ETFs

    // Crypto
    if (t.match(/^(BTC|ETH|BTCC|ETHE|GBTC)/) || t.includes('COIN')) return 'Crypto';

    // Bonds
    if (t.match(/^(TLT|AGG|BND|LQD|HYG|JNK|TIP)$/)) return 'Bond';

    // REITs
    if (t.match(/^(O|STAG|VNQ|IYR|XLRE)$/)) return 'REIT';

    // Commodities
    if (t.match(/^(GLD|SLV|USO|UNG|DBA|HMMJ|KILO)$/)) return 'Commodity';

    // Growth stocks (tech/high growth)
    if (t.match(/^(AAPL|MSFT|GOOGL|GOOG|AMZN|NVDA|TSLA|META|NFLX|AMD|CRM|ADBE|PLTR|RIVN|NIO|MVIS|CRSP|AIEQ|ABNB)$/)) return 'Growth';

    // Value stocks (established, dividend-paying)
    if (t.match(/^(BRK\.B|JPM|JNJ|PG|KO|PEP|WMT|HD|UNH|V|MA|DIS|MCD|NKE|CMCSA|PFE|VZ|T|CLX|CNK|CROX|SIRI|OXY|PR|HCC)$/)) return 'Value';

    // Canadian banks/utilities
    if (t.match(/^(TD|BNS|RY|BMO|CM|ENB|TRP|SU|CNQ|AQN|AC|RCI|TA|MG|NPI)$/)) return 'Value';

    // Default
    return 'Stock';
}

// Logic to determine the correct API ticker symbol based on currency
function resolveQuoteSymbol(pos) {
    const t = pos.ticker.toUpperCase();
    const isCAD = pos.currency === 'CAD';

    // If it's already suffixed, trust it
    if (t.includes('.')) return t;

    if (isCAD) {
        // KNOWN NEO CDRs (Canadian Depositary Receipts)
        // These trade in CAD but represent US stocks (PFE, AMZN, etc.)
        const neoCdrs = [
            'AMZN', 'AAPL', 'GOOG', 'GOOGL', 'MSFT', 'TSLA', 'NFLX', 'META', 'NVDA',
            'PFE', 'DIS', 'V', 'MA', 'PYPL', 'JPM', 'BAC', 'WMT', 'HD', 'COST',
            'PG', 'JNJ', 'KO', 'PEP', 'MCD', 'SBUX', 'NKE', 'INTC', 'AMD', 'IBM', 'ABNB'
        ];

        if (neoCdrs.includes(t)) {
            return `${t}.NE`;
        }

        // KNOWN TSX STOCKS (Need .TO)
        const tsxStocks = [
            'TD', 'RY', 'BNS', 'BMO', 'CM', 'ENB', 'TRP', 'CNQ', 'SU', 'ATD', 'CSU',
            'SHOP', 'BCE', 'T', 'NA', 'CP', 'CNR', 'BAM', 'SLF', 'MFC', 'TRI', 'GIB.A',
            'DOL', 'POW', 'QSR', 'FTS', 'EMA', 'AEM', 'WPM', 'K', 'CCO', 'FM', 'TECK.B',
            'RCI.B', 'L', 'WN', 'MRU', 'SAP', 'BYD', 'AC', 'AQN', 'CAR.UN', 'REI.UN',
            'VFV', 'VCN', 'VUN', 'XQQ', 'XIU', 'XIC', 'ZSP', 'ZEB', 'HMMJ', 'HIVE', 'BTCC', 'KILO',
            'TA', 'MG', 'NPI'
        ];

        if (tsxStocks.includes(t)) {
            return `${t}.TO`;
        }
    }

    return t;
}

// Modal Functions
function openCreatePortfolioModal() {
    document.getElementById('portfolio-modal').classList.remove('hidden');
    document.getElementById('portfolio-name').value = '';
    document.getElementById('portfolio-description').value = '';
}

function closePortfolioModal() {
    document.getElementById('portfolio-modal').classList.add('hidden');
}

function openAddPositionModal() {
    if (!currentPortfolioId) {
        alert('Please select a portfolio first');
        return;
    }
    document.getElementById('position-modal').classList.remove('hidden');
    document.getElementById('position-ticker').value = '';
    document.getElementById('position-quantity').value = '';
    document.getElementById('position-cost').value = '';
    document.getElementById('position-date').value = '';
    document.getElementById('position-notes').value = '';
    document.getElementById('position-category').value = 'Stock';
}

function closePositionModal() {
    document.getElementById('position-modal').classList.add('hidden');
}

// Paper Trading Trade Modal
let tradeState = {
    ticker: '',
    type: 'BUY',
    currentPrice: 0,
    availableCash: 0,
    currency: 'USD'
};

async function openTradeModal(ticker) {
    if (!currentPortfolioId) {
        alert('Please create or select a Paper Trading portfolio first!');
        switchTab('portfolio');
        return;
    }

    ticker = ticker.toUpperCase();
    tradeState.ticker = ticker;
    tradeState.type = 'BUY'; // Default

    document.getElementById('trade-ticker-badge').textContent = ticker;
    document.getElementById('trade-modal').classList.remove('hidden');
    document.getElementById('trade-quantity').value = '';

    // UI reset
    setTradeType('BUY');

    // Fetch live price
    document.getElementById('trade-current-price').textContent = 'Fetching...';
    try {
        const res = await fetch(`${API_BASE}/quotes?symbols=${ticker}`);
        const prices = await res.json();
        const price = prices[ticker] || 0;
        tradeState.currentPrice = price;
        document.getElementById('trade-current-price').textContent = `$${price.toFixed(2)}`;
        document.getElementById('trade-price').value = price.toFixed(2);
    } catch (e) {
        console.error('Error fetching price for trade:', e);
        document.getElementById('trade-current-price').textContent = 'N/A';
    }

    // Get available cash
    try {
        const res = await fetch(`${API_BASE}/portfolios/${currentPortfolioId}`);
        const p = await res.json();
        tradeState.availableCash = p.cash_usd; // For now default to USD
        document.getElementById('trade-available-cash').textContent = `$${p.cash_usd.toLocaleString()}`;
    } catch (e) {
        console.error('Error fetching cash:', e);
    }

    updateTradeTotal();
}

function closeTradeModal() {
    document.getElementById('trade-modal').classList.add('hidden');
}

function setTradeType(type) {
    tradeState.type = type;
    const buyBtn = document.getElementById('trade-buy-btn');
    const sellBtn = document.getElementById('trade-sell-btn');

    if (type === 'BUY') {
        buyBtn.className = 'flex-1 py-3 rounded-lg text-sm font-bold transition-all bg-green-500 text-white shadow-lg shadow-green-900/20';
        sellBtn.className = 'flex-1 py-3 rounded-lg text-sm font-bold transition-all text-gray-400 hover:text-white';
    } else {
        sellBtn.className = 'flex-1 py-3 rounded-lg text-sm font-bold transition-all bg-red-500 text-white shadow-lg shadow-red-900/20';
        buyBtn.className = 'flex-1 py-3 rounded-lg text-sm font-bold transition-all text-gray-400 hover:text-white';
    }
    updateTradeTotal();
}

function updateTradeTotal() {
    const qty = parseFloat(document.getElementById('trade-quantity').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;
    const total = qty * price;
    document.getElementById('trade-total').textContent = `$${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

async function submitTrade() {
    const qty = parseFloat(document.getElementById('trade-quantity').value);
    const price = parseFloat(document.getElementById('trade-price').value);

    if (!qty || qty <= 0) {
        alert('Please enter a valid quantity');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/portfolios/${currentPortfolioId}/trade`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: tradeState.ticker,
                type: tradeState.type,
                quantity: qty,
                price: price,
                currency: 'USD'
            })
        });

        const data = await res.json();
        if (data.error) {
            alert(`Trade Failed: ${data.error}`);
            return;
        }

        closeTradeModal();
        selectPortfolio(currentPortfolioId); // Refresh whole view
        alert(`Successfully ${tradeState.type === 'BUY' ? 'purchased' : 'sold'} ${qty} shares of ${tradeState.ticker}`);
    } catch (error) {
        console.error('Error submitting trade:', error);
        alert('Network error submitting trade');
    }
}

async function loadTradeHistory(portfolioId = currentPortfolioId) {
    if (!portfolioId) return;
    try {
        const res = await fetch(`${API_BASE}/portfolios/${portfolioId}/history`);
        const trades = await res.json();
        renderTradeHistory(trades);
    } catch (e) {
        console.error('Error loading trade history:', e);
    }
}

function renderTradeHistory(trades) {
    const tbody = document.getElementById('trade-history-body');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-8 text-center text-gray-500">No trades yet.</td></tr>';
        return;
    }

    tbody.innerHTML = trades.map(t => {
        const date = new Date(t.timestamp).toLocaleDateString();
        const typeClass = t.type === 'BUY' ? 'text-green-400' : 'text-red-400';
        const total = t.quantity * t.price;
        return `
            <tr class="hover:bg-gray-800/20">
                <td class="px-6 py-4 text-gray-400 text-xs">${date}</td>
                <td class="px-6 py-4 font-bold text-white">${t.ticker}</td>
                <td class="px-6 py-4"><span class="${typeClass} font-bold text-xs">${t.type}</span></td>
                <td class="px-6 py-4 text-right font-mono text-gray-300">${t.quantity}</td>
                <td class="px-6 py-4 text-right font-mono text-gray-300">$${t.price.toFixed(2)}</td>
                <td class="px-6 py-4 text-right font-mono font-bold text-white">$${total.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
            </tr>
        `;
    }).join('');
}

// Portfolio CRUD
async function savePortfolio(event) {
    event.preventDefault();

    const name = document.getElementById('portfolio-name').value;
    const description = document.getElementById('portfolio-description').value;

    try {
        const res = await fetch(`${API_BASE}/portfolios`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });

        const portfolio = await res.json();
        closePortfolioModal();
        await loadPortfolios();
        selectPortfolio(portfolio.id);
    } catch (error) {
        console.error('Error creating portfolio:', error);
        alert('Failed to create portfolio');
    }
}

async function loadPortfolios() {
    try {
        const res = await fetch(`${API_BASE}/portfolios`);
        portfolios = await res.json();
        renderPortfolioCards();

        // Restore last viewed portfolio
        const lastPortfolioId = localStorage.getItem(STORAGE_KEY_PORTFOLIO);
        if (lastPortfolioId && portfolios.find(p => p.id === lastPortfolioId)) {
            if (!currentPortfolioId) { // Only if not already selected (e.g. by manual click)
                selectPortfolio(lastPortfolioId);
            }
        }
    } catch (error) {
        console.error('Error loading portfolios:', error);
    }
}

function renderPortfolioCards() {
    const container = document.getElementById('portfolio-cards');

    if (portfolios.length === 0) {
        container.innerHTML = `
            <div class="glass-panel p-8 rounded-xl text-center col-span-3">
                <div class="text-gray-400 mb-4">No portfolios yet. Create one to start paper trading!</div>
                <button onclick="openCreatePortfolioModal()" 
                        class="px-4 py-2 bg-warren-accent hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-all">
                    Create Paper Trading Portfolio
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = portfolios.map(p => `
        <div onclick="selectPortfolio('${p.id}')" 
             class="glass-panel p-6 rounded-xl cursor-pointer hover:border-warren-accent transition-all ${currentPortfolioId === p.id ? 'border-2 border-warren-accent' : 'border border-gray-700'}">
            <h4 class="text-lg font-bold text-white mb-1">${p.name}</h4>
            <p class="text-xs text-gray-500 mb-3">${p.description || 'No description'}</p>
            <div class="flex justify-between items-center text-sm">
                <div>
                    <span class="text-green-400 font-mono font-bold">$${(p.cash_usd || 100000).toLocaleString()}</span>
                    <span class="text-gray-500 text-[10px] ml-1">CASH</span>
                </div>
                <button onclick="deletePortfolio('${p.id}', event)" 
                        class="text-red-400 hover:text-red-300 text-xs">Delete</button>
            </div>
        </div>
    `).join('');
}

async function selectPortfolio(portfolioId) {
    currentPortfolioId = portfolioId;
    localStorage.setItem(STORAGE_KEY_PORTFOLIO, portfolioId); // Persist selection

    renderPortfolioCards(); // Update selection highlight

    try {
        const res = await fetch(`${API_BASE}/portfolios/${portfolioId}`);
        const portfolio = await res.json();

        document.getElementById('selected-portfolio-name').textContent = portfolio.name;
        document.getElementById('selected-portfolio-desc').textContent = portfolio.description || 'No description';

        // Format last updated date
        const date = new Date(portfolio.updated_at);
        const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        document.getElementById('portfolio-updated-at').textContent = dateStr;

        // Cash Balances
        document.getElementById('portfolio-cash-usd').textContent = `$${(portfolio.cash_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
        document.getElementById('portfolio-cash-cad').textContent = `C$${(portfolio.cash_cad || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

        // Show details section
        document.getElementById('portfolio-details').classList.remove('hidden');

        // Load positions with live prices
        await loadPositions(portfolio.positions);

        // Load Trade History
        loadTradeHistory(portfolioId);
    } catch (error) {
        console.error('Error loading portfolio:', error);
    }
}

async function deletePortfolio(portfolioId, event) {
    event.stopPropagation();

    if (!confirm('Delete this portfolio? This cannot be undone.')) return;

    try {
        await fetch(`${API_BASE}/portfolios/${portfolioId}`, { method: 'DELETE' });

        if (currentPortfolioId === portfolioId) {
            currentPortfolioId = null;
            localStorage.removeItem(STORAGE_KEY_PORTFOLIO); // Clear persistence
            document.getElementById('portfolio-details').classList.add('hidden');
        }

        await loadPortfolios();
    } catch (error) {
        console.error('Error deleting portfolio:', error);
        alert('Failed to delete portfolio');
    }
}

// Position Management
async function savePosition(event) {
    event.preventDefault();

    const ticker = document.getElementById('position-ticker').value.toUpperCase();
    const quantity = parseFloat(document.getElementById('position-quantity').value);
    const avg_cost = parseFloat(document.getElementById('position-cost').value);
    const purchase_date = document.getElementById('position-date').value || null;
    const notes = document.getElementById('position-notes').value;
    const category = document.getElementById('position-category').value;

    try {
        await fetch(`${API_BASE}/portfolios/${currentPortfolioId}/positions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker, quantity, avg_cost, purchase_date, notes, category })
        });

        closePositionModal();
        selectPortfolio(currentPortfolioId); // Reload
    } catch (error) {
        console.error('Error adding position:', error);
        alert('Failed to add position');
    }
}

async function deletePosition(positionId) {
    if (!confirm('Remove this position?')) return;

    try {
        await fetch(`${API_BASE}/positions/${positionId}`, { method: 'DELETE' });
        selectPortfolio(currentPortfolioId); // Reload
    } catch (error) {
        console.error('Error deleting position:', error);
        alert('Failed to delete position');
    }
}

function sortPortfolio(column) {
    if (sortState.column === column) {
        // Toggle direction
        sortState.direction = sortState.direction === 'asc' ? 'desc' : 'asc';
    } else {
        sortState.column = column;
        sortState.direction = 'desc'; // Default to descending for new columns (usually values/gains)
    }

    renderPositionsTable();
}

async function loadPositions(positions) {
    const tbody = document.getElementById('holdings-table-body');

    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-8 text-center text-gray-500">No positions yet. Add your first position!</td></tr>';
        document.getElementById('portfolio-total-value').textContent = '$0.00';
        document.getElementById('portfolio-total-gain').textContent = '$0.00 (0%)';
        currentRefreshedPositions = [];
        // Clear chart
        const ctx = document.getElementById('allocation-chart');
        if (allocationChart) allocationChart.destroy();
        return;
    }

    // Show loading state initially
    tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-8 text-center text-warren-accent">Loading live prices...</td></tr>';

    try {
        // Auto-categorize positions if they don't have a category
        positions = positions.map(pos => {
            if (!pos.category || pos.category === 'Stock') {
                pos.category = autoCategorize(pos.ticker);
            }
            return pos;
        });

        // PROGRESSIVE LOADING: Fetch prices and render as they arrive
        currentRefreshedPositions = [];

        // First, show all positions with placeholder prices
        positions.forEach(pos => {
            currentRefreshedPositions.push({
                ...pos,
                currentPrice: pos.avg_cost, // Use avg_cost as placeholder
                value: pos.quantity * pos.avg_cost,
                gain: 0,
                gainPct: 0,
                loading: true
            });
        });

        // Render initial table with placeholders
        renderPositionsTable();

        // Prepare list of symbols to fetch, resolving .NE/.TO based on currency
        const symbolMap = {}; // Maps original ticker to query symbol
        const symbolsToFetch = [];

        positions.forEach(p => {
            const querySymbol = resolveQuoteSymbol(p);
            symbolMap[p.ticker] = querySymbol;
            if (!symbolsToFetch.includes(querySymbol)) {
                symbolsToFetch.push(querySymbol);
            }
        });

        // Now fetch prices progressively
        const priceData = await fetchLivePrices(symbolsToFetch);

        // Update positions with real prices
        currentRefreshedPositions = positions.map(pos => {
            const querySymbol = symbolMap[pos.ticker];

            // Get price using the resolved symbol
            let currentPrice = priceData[querySymbol] || 0;

            // Fallback: If 0, maybe the backend stripped the suffix? Try original.
            if ((currentPrice === 0 || currentPrice === undefined) && priceData[pos.ticker]) {
                currentPrice = priceData[pos.ticker];
            }
            // Another Fallback: If query was .NE but backend returned .TO or something else?

            // Final fallback to avg_cost if still 0/undefined
            if (!currentPrice) currentPrice = pos.avg_cost;

            const value = pos.quantity * currentPrice;
            const cost = pos.quantity * pos.avg_cost;
            const gain = value - cost;
            const gainPct = (cost !== 0) ? (gain / cost) * 100 : 0;

            return {
                ...pos,
                currentPrice,
                value,
                gain,
                gainPct,
                loading: false
            };
        });

        // Final render with real prices
        renderPositionsTable();

    } catch (error) {
        console.error('Error loading positions:', error);
        tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-8 text-center text-red-400">Error loading prices</td></tr>';
    }
}

function renderPositionsTable() {
    const tbody = document.getElementById('holdings-table-body');
    // Clear existing content
    tbody.innerHTML = '';

    // Split positions by currency (inferred from ticker suffix or explicit currency)
    const usdPositions = [];
    const cadPositions = [];

    // Helper to determine if position is CAD
    const isCAD = (pos) => {
        // Explicit currency check
        if (pos.currency === 'CAD') return true;
        // Ticker pattern check
        const t = pos.ticker.toUpperCase();
        return t.endsWith('.TO') || t.endsWith('.NE') || t.endsWith('.V') || t.endsWith('.CN');
    };

    const sortFn = (a, b) => {
        let valA = a[sortState.column];
        let valB = b[sortState.column];

        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();

        if (valA < valB) return sortState.direction === 'asc' ? -1 : 1;
        if (valA > valB) return sortState.direction === 'asc' ? 1 : -1;
        return 0;
    };

    currentRefreshedPositions.forEach(pos => {
        if (isCAD(pos)) cadPositions.push(pos);
        else usdPositions.push(pos);
    });

    usdPositions.sort(sortFn);
    cadPositions.sort(sortFn);

    let totalValue = 0;
    let totalCost = 0;

    const renderSection = (positions, title, currencySymbol) => {
        if (positions.length === 0) return;

        // Section Title
        const headerRow = document.createElement('tr');
        headerRow.innerHTML = `<td colspan="7" class="px-6 py-3 bg-gray-800/80 text-gray-300 font-bold border-b border-gray-700">${title} (${positions.length})</td>`;
        tbody.appendChild(headerRow);

        positions.forEach(pos => {
            totalValue += pos.value;
            totalCost += (pos.quantity * pos.avg_cost);

            const gainClass = pos.gain >= 0 ? 'text-green-400' : 'text-red-400';

            const row = document.createElement('tr');
            row.className = 'hover:bg-gray-800/50 transition-colors border-b border-gray-800/20';
            row.innerHTML = `
                <td class="px-6 py-4">
                    <a href="https://www.tradingview.com/symbols/${pos.ticker}/" target="_blank" 
                       class="font-bold text-white hover:text-blue-400 underline decoration-dotted">
                        ${pos.ticker}
                    </a>
                    <div class="text-xs text-gray-500">${pos.category || 'Stock'}</div>
                </td>
                <td class="px-6 py-4 text-right text-gray-300 font-mono">${pos.quantity.toFixed(4)}</td>
                <td class="px-6 py-4 text-right text-gray-300 font-mono">${currencySymbol}${pos.avg_cost.toFixed(2)}</td>
                <td class="px-6 py-4 text-right text-white font-mono">${currencySymbol}${pos.currentPrice.toFixed(2)}</td>
                <td class="px-6 py-4 text-right text-white font-bold font-mono">${currencySymbol}${pos.value.toFixed(2)}</td>
                <td class="px-6 py-4 text-right ${gainClass} font-mono">
                    ${pos.gain >= 0 ? '+' : ''}${currencySymbol}${pos.gain.toFixed(2)} <span class="opacity-70 text-xs text-gray-400">(${pos.gainPct.toFixed(1)}%)</span>
                </td>
                <td class="px-6 py-4 text-right">
                    <div class="flex items-center justify-end gap-2">
                        <button onclick="openSignalPopup('${pos.ticker}')"
                                class="text-blue-400 hover:text-blue-300 text-xs bg-blue-900/20 px-2 py-1 rounded border border-blue-500/20 hover:border-blue-400/40 transition-all"
                                title="View Entry/Exit Signals">📊 Signals</button>
                        <button onclick="deletePosition('${pos.id}')" 
                                class="text-red-400 hover:text-red-300 text-xs bg-red-900/20 px-2 py-1 rounded border border-red-500/20">Remove</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    };

    renderSection(usdPositions, '🇺🇸 USD Assets', '$');
    renderSection(cadPositions, '🇨🇦 CAD Assets', 'C$');

    // Signals are now loaded inline per-ticker row on demand
    // (toggled by the 📊 Signals button in each row's Actions cell)

    // Update headers to show sort direction
    document.querySelectorAll('th[onclick^="sortPortfolio"]').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (icon) { // Check if icon exists
            if (th.getAttribute('onclick').includes(`('${sortState.column}')`)) {
                icon.textContent = sortState.direction === 'asc' ? '↑' : '↓';
                icon.classList.remove('opacity-50');
                icon.classList.add('text-white');
            } else {
                icon.textContent = '↕';
                icon.classList.add('opacity-50');
                icon.classList.remove('text-white');
            }
        }
    });

    // Update totals
    const totalGain = totalValue - totalCost;
    const totalGainPct = totalCost > 0 ? (totalGain / totalCost) * 100 : 0;
    const gainClass = totalGain >= 0 ? 'text-green-400' : 'text-red-400';

    document.getElementById('portfolio-total-value').textContent = `$${totalValue.toFixed(2)}`;
    document.getElementById('portfolio-total-gain').innerHTML = `
        <span class="${gainClass}">${totalGain >= 0 ? '+' : ''}$${totalGain.toFixed(2)} (${totalGainPct.toFixed(1)}%)</span>
    `;

    // Update Chart
    updateAllocationChart(currentRefreshedPositions);
}


let allocationChart = null;
let allocationMode = 'ticker'; // 'ticker' or 'category'

function toggleAllocationMode() {
    console.log('Toggling allocation mode. Current:', allocationMode);

    // Safety check - empty array is truthy, so check length
    if (!currentRefreshedPositions || currentRefreshedPositions.length === 0) {
        console.warn('No positions data available to toggle.');
        return;
    }

    allocationMode = allocationMode === 'ticker' ? 'category' : 'ticker';
    updateAllocationChart(currentRefreshedPositions);

    // Update button text
    const btn = document.getElementById('allocation-toggle-btn');
    if (btn) btn.textContent = allocationMode === 'ticker' ? 'View by Strategy' : 'View by Ticker';
}

function updateAllocationChart(positions) {
    const ctx = document.getElementById('allocation-chart');
    if (!ctx) return;

    if (allocationChart) {
        allocationChart.destroy();
    }

    if (positions.length === 0) return;

    const totalValue = positions.reduce((sum, p) => sum + p.value, 0);
    let chartData = [];

    if (allocationMode === 'ticker') {
        let otherValue = 0;
        const sortedPos = [...positions].sort((a, b) => b.value - a.value);

        sortedPos.forEach(p => {
            if (p.value / totalValue < 0.05 && sortedPos.length > 5) {
                otherValue += p.value;
            } else {
                chartData.push({ label: p.ticker, value: p.value });
            }
        });

        if (otherValue > 0) chartData.push({ label: 'Other', value: otherValue });

    } else {
        // Group by Category
        const categories = {};
        positions.forEach(p => {
            const cat = p.category || 'Stock';
            if (!categories[cat]) {
                categories[cat] = { value: 0, tickers: [] };
            }
            categories[cat].value += p.value;
            categories[cat].tickers.push({ t: p.ticker, v: p.value });
        });

        // Convert to array and handle tooltips
        chartData = Object.keys(categories)
            .map(k => {
                // Sort tickers by value to show top ones
                const topTickers = categories[k].tickers
                    .sort((a, b) => b.v - a.v)
                    .map(item => item.t)
                    .slice(0, 4) // Show top 4
                    .join(', ');

                const count = categories[k].tickers.length;
                const suffix = count > 4 ? ` +${count - 4}` : '';

                return {
                    label: k,
                    value: categories[k].value,
                    tooltipExtra: `${topTickers}${suffix}`
                };
            })
            .sort((a, b) => b.value - a.value);
    }

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: chartData.map(d => d.label),
            datasets: [{
                data: chartData.map(d => d.value),
                backgroundColor: [
                    '#38bdf8', '#22c55e', '#eab308', '#ef4444',
                    '#a855f7', '#f97316', '#6366f1', '#ec4899', '#64748b'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#94a3b8', boxWidth: 12 }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            const value = context.raw;
                            const total = context.chart._metasets[context.datasetIndex].total;
                            const pct = ((value / total) * 100).toFixed(1);

                            // Get custom tooltip data
                            const item = chartData[context.dataIndex];
                            const extra = (item && item.tooltipExtra) ? ` (${item.tooltipExtra})` : '';

                            return ` ${context.label}: $${value.toLocaleString()} (${pct}%)${extra}`;
                        }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

async function fetchLivePrices(tickers) {
    if (tickers.length === 0) return {};

    try {
        const symbols = tickers.join(',');
        console.log(`Fetching prices for: ${symbols}`);
        const res = await fetch(`${API_BASE}/quotes?symbols=${symbols}`);

        if (!res.ok) throw new Error(`API Error: ${res.status}`);

        const prices = await res.json();
        console.log('Received prices:', prices);
        return prices;
    } catch (error) {
        console.error('Error fetching batch prices:', error);
        return {};
    }
}

// Initialize portfolio view when tab is switched
function initPortfolioView() {
    loadPortfolios();
}

// Import Function
async function importWealthSimple(input) {
    if (!input.files || !input.files[0]) return;

    if (!currentPortfolioId) {
        alert('Please create or select a portfolio first!');
        input.value = '';
        return;
    }

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    const btn = document.querySelector('button[onclick*="pdf-upload"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = `Parsing...`;

    try {
        const res = await fetch(`${API_BASE}/import/pdf`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Failed to parse PDF');

        const positions = await res.json();
        await _importPositions(positions, 'PDF');
    } catch (error) {
        console.error('Error importing PDF:', error);
        alert('Error importing PDF: ' + error.message);
    } finally {
        btn.innerHTML = originalText;
        input.value = '';
    }
}

async function _importPositions(positions, label) {
    if (!positions || positions.length === 0) {
        alert('No positions found.');
        return;
    }

    const replace = confirm(`${label}: ${positions.length} positions found.\n\nReplace existing positions? (Yes = overwrite, No = add to existing)`);

    if (replace) {
        const delRes = await fetch(`${API_BASE}/portfolios/${currentPortfolioId}`);
        const portfolio = await delRes.json();
        const existing = portfolio.positions || [];
        for (const pos of existing) {
            await fetch(`${API_BASE}/positions/${pos.id}`, { method: 'DELETE' }).catch(() => {});
        }
    }

    let successCount = 0;
    for (const pos of positions) {
        try {
            await fetch(`${API_BASE}/portfolios/${currentPortfolioId}/positions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticker: pos.ticker, quantity: pos.quantity, avg_cost: pos.avg_cost,
                    notes: pos.notes || '', category: pos.category || 'Stock'
                })
            });
            successCount++;
        } catch (e) {
            console.error(`Failed to import ${pos.ticker}`, e);
        }
    }
    alert(`${replace ? 'Replaced with' : 'Added'} ${successCount} of ${positions.length} positions!`);
    selectPortfolio(currentPortfolioId);
}

// --- Import from Server ---
async function importFromServerFiles() {
    if (!currentPortfolioId) {
        alert('Please create or select a portfolio first!');
        return;
    }

    try {
        const listRes = await fetch(`${API_BASE}/import/portfolio-files`);
        const listData = await listRes.json();
        const files = listData.files || [];

        if (files.length === 0) {
            alert('No portfolio files found on the server.');
            return;
        }

        const fileList = files.map(f => `  • ${f.name} (${(f.size_bytes / 1024).toFixed(0)}KB)`).join('\n');
        if (!confirm(`Found ${files.length} file(s) on server:\n${fileList}\n\nImport positions from these files?`)) return;

        const res = await fetch(`${API_BASE}/import/from-server-files`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const positions = await res.json();
        await _importPositions(positions, 'Server files');
    } catch (err) {
        console.error('Import from server failed:', err);
        alert('Import failed: ' + err.message);
    }
}

async function importCSV(input) {
    if (!input.files || !input.files[0]) return;
    if (!currentPortfolioId) {
        alert('Please create or select a portfolio first!');
        input.value = '';
        return;
    }

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE}/import/csv`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Failed to parse CSV');
        const positions = await res.json();
        await _importPositions(positions, 'CSV');
    } catch (err) {
        console.error('CSV import failed:', err);
        alert('CSV import failed: ' + err.message);
    } finally {
        input.value = '';
    }
}

// --- Signal Popup (glassmorphism floating dialog) ---

// Cache: ticker -> rendered HTML so we don't re-fetch on re-open
const _signalCache = {};

function openSignalPopup(ticker) {
    const dialog  = document.getElementById('signal-popup-dialog');
    const body    = document.getElementById('signal-popup-body');
    const badge   = document.getElementById('signal-popup-ticker-badge');
    const closeBtn = document.getElementById('signal-popup-close');
    if (!dialog || !body) return;

    // Update header badge
    badge.textContent = ticker;

    // Show cached content instantly, or show loader and fetch
    if (_signalCache[ticker]) {
        body.innerHTML = _signalCache[ticker];
    } else {
        body.innerHTML = '<div style="padding:24px;text-align:center;color:#64748b;font-size:13px" class="animate-pulse">Loading signals…</div>';
        loadTickerSignals(ticker, 'signal-popup-body').then(() => {
            _signalCache[ticker] = body.innerHTML;
        }).catch(() => {});
    }

    // Open as modal (top-layer, focus-trapped, Esc closes)
    dialog.showModal();

    // Close button
    closeBtn.onclick = () => dialog.close();

    // Light-dismiss fallback for Safari (closedby="any" not yet supported)
    if (!('closedBy' in HTMLDialogElement.prototype)) {
        dialog.addEventListener('click', function lightDismiss(e) {
            if (e.target !== dialog) return;
            const r = dialog.getBoundingClientRect();
            const inside = r.top <= e.clientY && e.clientY <= r.top + r.height &&
                           r.left <= e.clientX && e.clientX <= r.left + r.width;
            if (!inside) {
                dialog.close();
                dialog.removeEventListener('click', lightDismiss);
            }
        });
    }
}

// --- Window Exports ---
window.openCreatePortfolioModal = openCreatePortfolioModal;
window.closePortfolioModal = closePortfolioModal;
window.openAddPositionModal = openAddPositionModal;
window.closePositionModal = closePositionModal;
window.openTradeModal = openTradeModal;
window.closeTradeModal = closeTradeModal;
window.setTradeType = setTradeType;
window.submitTrade = submitTrade;
window.savePortfolio = savePortfolio;
window.selectPortfolio = selectPortfolio;
window.deletePortfolio = deletePortfolio;
window.savePosition = savePosition;
window.deletePosition = deletePosition;
window.sortPortfolio = sortPortfolio;
window.toggleAllocationMode = toggleAllocationMode;
window.initPortfolioView = initPortfolioView;
window.importWealthSimple = importWealthSimple;
window.importFromServerFiles = importFromServerFiles;
window.importCSV = importCSV;
window.openSignalPopup = openSignalPopup;
