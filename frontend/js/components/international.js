import { fetchJson } from '../api.js';

export async function initInternational() {
    const indiaContainer = document.getElementById('india-picks-container');
    const canadaContainer = document.getElementById('canada-picks-container');
    const title = document.getElementById('international-title');

    if (!indiaContainer || !canadaContainer) return;

    // Loading State
    indiaContainer.innerHTML = '<div class="col-span-3 text-center py-12 text-gray-500 animate-pulse">Scanning Mumbai (NSE)...</div>';
    canadaContainer.innerHTML = '<div class="col-span-3 text-center py-12 text-gray-500 animate-pulse">Scanning Toronto (TSX)...</div>';

    try {
        const data = await fetchJson('/api/international/picks');

        title.innerHTML = 'Global Market Picks 🌍';
        document.getElementById('international-subtitle').innerText = 'Quantitative deep value and growth scans for Top Emerging and Developed markets';

        const indiaPicks = data["India (Emerging Market)"] || [];
        const canadaPicks = data["Canada (Developed Market)"] || [];

        indiaContainer.innerHTML = '';
        if (indiaPicks.length === 0) {
            indiaContainer.innerHTML = '<div class="col-span-3 text-center text-gray-500">No data available for India</div>';
        } else {
            indiaPicks.forEach(pick => {
                indiaContainer.appendChild(createInternationalCard(pick));
            });
        }

        canadaContainer.innerHTML = '';
        if (canadaPicks.length === 0) {
            canadaContainer.innerHTML = '<div class="col-span-3 text-center text-gray-500">No data available for Canada</div>';
        } else {
            canadaPicks.forEach(pick => {
                canadaContainer.appendChild(createInternationalCard(pick));
            });
        }

    } catch (error) {
        console.error("Error loading international picks:", error);
        indiaContainer.innerHTML = '<div class="col-span-3 text-center text-red-400">Failed to load data</div>';
        canadaContainer.innerHTML = '<div class="col-span-3 text-center text-red-400">Failed to load data</div>';
    }
}

function createInternationalCard(stock) {
    const div = document.createElement('div');
    div.className = 'glass-panel p-6 rounded-2xl flex flex-col h-full hover:-translate-y-1 transition-transform cursor-pointer group border border-gray-800 hover:border-warren-accent';

    const isPositive = stock.change_pct >= 0;
    const colorClass = isPositive ? 'text-warren-success' : 'text-warren-danger';
    const sign = isPositive ? '+' : '';

    div.innerHTML = `
        <div class="flex justify-between items-start mb-4">
            <div>
                <a href="https://www.tradingview.com/symbols/${stock.tv_symbol}/" target="_blank" rel="noopener noreferrer" class="text-2xl font-black text-white hover:text-blue-400 transition-colors underline decoration-dotted decoration-gray-600 hover:decoration-blue-400 inline-block mb-1" title="View on TradingView">
                    ${stock.symbol}
                </a>
                <div class="text-xs text-gray-400 font-medium truncate max-w-[150px]" title="${stock.name}">${stock.name}</div>
                <div class="text-[10px] bg-gray-800 text-gray-300 px-2 py-0.5 rounded mt-2 inline-block">${stock.type}</div>
            </div>
            <div class="text-right">
                <div class="text-xl font-mono text-white">$${stock.price}</div>
                <div class="text-sm font-bold ${colorClass}">${sign}${stock.change_pct}%</div>
                 <div class="text-[10px] text-gray-500 mt-1 uppercase">Price</div>
            </div>
        </div>
        
        <p class="text-sm text-gray-400 mb-6 flex-grow line-clamp-2">${stock.description}</p>
        
        <div class="grid grid-cols-2 gap-3 mb-6 bg-gray-900/50 p-3 rounded-xl border border-gray-800/50">
            <div>
                <div class="text-[10px] text-gray-500 uppercase">ROE</div>
                <div class="font-mono text-white ${stock.roe > 15 ? 'text-green-400' : ''}">${stock.roe}%</div>
            </div>
            <div>
                <div class="text-[10px] text-gray-500 uppercase">Margin</div>
                <div class="font-mono text-white">${stock.margin}%</div>
            </div>
            <div>
                <div class="text-[10px] text-gray-500 uppercase">Growth</div>
                <div class="font-mono text-white ${stock.rev_growth > 10 ? 'text-green-400' : ''}">${stock.rev_growth}%</div>
            </div>
             <div>
                <div class="text-[10px] text-gray-500 uppercase">P/E</div>
                <div class="font-mono text-white">${stock.pe}</div>
            </div>
        </div>

        <div class="pt-4 border-t border-gray-800 flex justify-between items-center">
            <span class="text-xs text-gray-500 uppercase font-bold tracking-wider">Moat Score</span>
            <div class="flex items-center gap-2">
                <div class="w-24 h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div class="h-full bg-warren-accent" style="width: ${stock.moat_score}%"></div>
                </div>
                <span class="text-lg font-black text-white">${stock.moat_score}</span>
            </div>
        </div>
    `;

    return div;
}
