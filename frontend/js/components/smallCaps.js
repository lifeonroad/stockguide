import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export async function loadSmallCaps() {
    const container = document.getElementById('small-caps-container');
    const summaryContainer = document.getElementById('small-caps-summary');
    const notesContainer = document.getElementById('small-caps-notes');
    const notesList = document.getElementById('small-caps-notes-list');

    if (!container) return;

    const growth = document.getElementById('small-cap-filter-growth')?.value || '0.05';
    const pe = document.getElementById('small-cap-filter-pe')?.value || '25';
    const roe = document.getElementById('small-cap-filter-roe')?.value || '0.10';

    container.innerHTML = '<div class="col-span-full text-center text-warren-accent animate-pulse py-20">Scanning institutional gems & hidden growth...</div>';

    try {
        const res = await fetch(`${API_BASE}/small-caps?min_growth=${growth}&max_pe=${pe}&min_roe=${roe}`);
        if (!res.ok) throw new Error('API error');
        const data = await res.json();

        if (summaryContainer && data.data && data.data.length > 0) {
            const topGem = data.data[0];
            const avgScore = Math.round(data.data.reduce((acc, curr) => acc + curr.gem_score, 0) / data.data.length);

            summaryContainer.innerHTML = `
                <div class="glass-panel p-5 rounded-2xl border border-blue-500/30 bg-blue-500/5">
                    <div class="text-[10px] text-blue-400 uppercase font-bold tracking-widest mb-1">Top Rated Gem</div>
                    <div class="text-2xl font-black text-white">$${linkTV(topGem.symbol)}</div>
                    <div class="text-xs text-gray-400 mt-1">${topGem.name} | Score: ${topGem.gem_score}</div>
                </div>
                <div class="glass-panel p-5 rounded-2xl border border-warren-accent/30">
                    <div class="text-[10px] text-warren-accent uppercase font-bold tracking-widest mb-1">Avg Gem Score</div>
                    <div class="text-2xl font-black text-white">${avgScore}/100</div>
                    <div class="text-xs text-gray-400 mt-1">Found ${data.data.length} undervalued opportunities</div>
                </div>
                <div class="glass-panel p-5 rounded-2xl border border-green-500/30">
                    <div class="text-[10px] text-green-400 uppercase font-bold tracking-widest mb-1">Market Segment</div>
                    <div class="text-2xl font-black text-white">$300M - $3B</div>
                    <div class="text-xs text-gray-400 mt-1">Underserved high-growth small caps</div>
                </div>
            `;
        }

        if (notesContainer && data.notes) {
            notesContainer.classList.remove('hidden');
            notesList.innerHTML = data.notes.map(note => `<li class="leading-relaxed"><strong class="text-gray-300">Note:</strong> ${note}</li>`).join('');
        }

        container.innerHTML = '';
        if (data.data.length === 0) {
            container.innerHTML = '<div class="col-span-full text-center text-gray-500 py-10 italic">No gems currently meet for the strict growth/value criteria.</div>';
            return;
        }

        data.data.forEach(item => {
            const card = document.createElement('div');
            card.className = 'glass-panel p-6 rounded-2xl border-l-4 transition-all hover:bg-gray-800/40 flex flex-col h-full group';

            const colorClass = item.gem_score > 75 ? 'border-green-500' : 'border-blue-500';
            const badgeClass = item.gem_score > 75 ? 'bg-green-500/10 text-green-400' : 'bg-blue-500/10 text-blue-400';

            card.classList.add(colorClass);

            card.innerHTML = `
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <div class="flex items-baseline gap-2">
                            <h4 class="text-xl font-black text-white">${linkTV(item.symbol)}</h4>
                            <span class="text-[8px] text-gray-500 uppercase tracking-tighter">${item.sector}</span>
                        </div>
                        <p class="text-[10px] text-warren-accent font-bold uppercase truncate max-w-[120px]">${item.name}</p>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-mono text-white">$${item.price}</div>
                        <div class="text-[9px] text-gray-500 uppercase font-bold tracking-widest">${item.market_cap}M Cap</div>
                    </div>
                </div>

                <p class="text-[10px] text-gray-400 italic leading-relaxed mb-6 flex-grow line-clamp-3">
                    "${item.desc}"
                </p>

                <div class="grid grid-cols-2 gap-3 mb-6">
                    <div class="bg-gray-900/50 p-2 rounded-lg text-center">
                        <div class="text-[8px] text-gray-500 uppercase">P/E Ratio</div>
                        <div class="text-sm font-mono text-white">${item.pe}</div>
                    </div>
                    <div class="bg-gray-900/50 p-2 rounded-lg text-center">
                        <div class="text-[8px] text-gray-500 uppercase">Rev Growth</div>
                        <div class="text-sm font-mono text-green-400">+${item.rev_growth}%</div>
                    </div>
                </div>

                <div class="mt-auto pt-4 border-t border-gray-800/50">
                    <div class="flex justify-between items-center mb-2">
                        <span class="px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-widest ${badgeClass}">${item.sentiment}</span>
                        <div class="text-[9px] text-gray-500">Gem Score: <span class="text-white font-bold">${item.gem_score}/100</span></div>
                    </div>
                    <div class="h-1.5 w-full bg-gray-900 rounded-full overflow-hidden">
                        <div class="h-full bg-gradient-to-r from-blue-500 to-warren-accent group-hover:from-warren-accent group-hover:to-green-400 transition-all duration-500" style="width: ${item.gem_score}%"></div>
                    </div>
                    <div class="mt-3 text-[8px] text-gray-600 flex justify-between">
                        <span>P/B: ${item.pb}</span>
                        <span>ROE: ${item.roe}%</span>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });

    } catch (err) {
        console.error('Failed to load small-cap gems', err);
        container.innerHTML = '<div class="col-span-full text-center text-red-400 py-10">Failed to load gems. Try again later.</div>';
    }
}
