import { API_BASE } from '../api.js';
import { linkTV } from '../utils.js';

export async function loadGuruFlow() {
    const view = document.getElementById('guru-flow-view');
    if (!view) return;

    try {
        const res = await fetch(`${API_BASE}/guru-flow`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.error) {
            view.innerHTML = `<div class="text-center py-12 text-red-400">${data.error}</div>`;
            return;
        }

        const s = data.stats || {};
        setText('gf-stat-holdings', s.total_holdings ?? '--');
        setText('gf-stat-buys', s.total_buying_managers ?? '--');
        setText('gf-stat-sells', s.total_selling_managers ?? '--');
        setText('gf-stat-new', s.new_positions_count ?? '--');

        renderWidelyHeld(data.widely_held);
        renderActivityTable('gf-buys-body', data.top_buys, 'Most Bought');
        renderActivityTable('gf-sells-body', data.top_sells, 'Most Sold');
        renderNewPositions(data.new_positions);
        renderSustainedBuys(data.sustained_buys);
        renderHeavyBets(data.single_heavy_bets);
        renderNearLow(data.near_low);
        renderRotation(data.sector_rotation);
    } catch (err) {
        view.innerHTML = `<div class="text-center py-12 text-red-400">Failed to load: ${err.message}</div>`;
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function parseNum(val) {
    if (val === undefined || val === null || val === '') return -Infinity;
    if (typeof val === 'number') return val;
    const cleaned = String(val).replace(/[$,%+\s]/g, '');
    const n = parseFloat(cleaned);
    return isNaN(n) ? -Infinity : n;
}

function makeSortable(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const thead = table.querySelector('thead');
    if (!thead) return;
    const headers = thead.querySelectorAll('th');
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    headers.forEach((th, colIdx) => {
        th.style.cursor = 'pointer';
        th.style.userSelect = 'none';
        const sortKey = th.getAttribute('data-sort') || th.textContent.trim().toLowerCase();
        th.addEventListener('click', () => {
            const asc = th.dataset.dir !== 'asc';
            headers.forEach(h => { h.dataset.dir = ''; h.innerHTML = h.innerHTML.replace(/ [▲▼]$/, ''); });
            th.dataset.dir = asc ? 'asc' : 'desc';
            th.innerHTML = th.innerHTML.replace(/ [▲▼]$/, '') + (asc ? ' ▲' : ' ▼');

            const rows = Array.from(tbody.querySelectorAll('tr'));
            const bodyId = tbody.id || tableId + '-body';

            rows.sort((a, b) => {
                const aCell = a.children[colIdx];
                const bCell = b.children[colIdx];
                if (!aCell || !bCell) return 0;

                let aVal = aCell.textContent.trim();
                let bVal = bCell.textContent.trim();

                const aNum = parseNum(aVal);
                const bNum = parseNum(bVal);

                if (aNum !== -Infinity && bNum !== -Infinity) {
                    return asc ? aNum - bNum : bNum - aNum;
                }
                return asc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
            });

            rows.forEach(r => tbody.appendChild(r));
        });
    });
}

function fillTable(bodyId, items, rowFn) {
    const tbody = document.getElementById(bodyId);
    if (!tbody) return;
    if (!items || items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="px-4 py-8 text-center text-gray-500 italic">No data</td></tr>';
        return;
    }
    tbody.innerHTML = items.map((item, i) => `<tr class="hover:bg-gray-800/30 transition-colors">${rowFn(item, i)}</tr>`).join('');
}

function renderWidelyHeld(items) {
    fillTable('gf-widely-held-body', items, (h, i) => `
        <td class="px-4 py-2.5 text-gray-500">${i + 1}</td>
        <td class="px-4 py-2.5 font-bold text-white">${linkTV(h.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${h.name || ''}</td>
        <td class="px-4 py-2.5 text-center">${h.ownership_count || '0'}</td>
        <td class="px-4 py-2.5 text-right font-mono text-white">${h.portfolio_pct || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.max_pct || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono text-white">${h.current_price || ''}</td>
    `);
    makeSortable('gf-widely-held-table');
}

function renderActivityTable(bodyId, items, label) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    const table = body.closest('table') || document.querySelector(`#${bodyId}`)?.closest('table');
    fillTable(bodyId, items, a => {
        const pct = a.total_pct_change !== undefined && a.total_pct_change !== null
            ? (a.total_pct_change > 0 ? '+' : '') + a.total_pct_change.toFixed(1) + '%'
            : '';
        const is6mo = a.in_6mo;
        const color = label === 'Most Bought' ? 'text-green-400' : 'text-red-400';
        return `
        <td class="px-3 py-2.5 font-bold text-white">${linkTV(a.symbol || '?')}</td>
        <td class="px-3 py-2.5 text-gray-400 text-xs max-w-[90px] truncate">${a.name || ''}</td>
        <td class="px-3 py-2.5 text-center">${a.manager_count || '0'}</td>
        <td class="px-3 py-2.5 text-center">${is6mo ? '<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300">6mo</span>' : '<span class="text-gray-600 text-xs">—</span>'}</td>
        <td class="px-3 py-2.5 text-right font-mono ${color}">${pct}</td>
        <td class="px-3 py-2.5 text-right font-mono text-white">${a.current_price || ''}</td>
    `});
    if (table) makeSortable(table.id);
}

function renderNewPositions(items) {
    fillTable('gf-new-body', items, a => `
        <td class="px-4 py-2.5 font-bold text-purple-300">${linkTV(a.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${a.name || ''}</td>
        <td class="px-4 py-2.5 text-center">${a.manager_count || '0'}</td>
        <td class="px-4 py-2.5 text-center">${a.in_6mo ? '<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300">6mo</span>' : '<span class="text-gray-600 text-xs">—</span>'}</td>
        <td class="px-4 py-2.5 text-right font-mono text-green-400">${a.total_pct_change ? '+' + a.total_pct_change.toFixed(1) + '%' : ''}</td>
    `);
    makeSortable('gf-new-table');
}

function renderSustainedBuys(items) {
    const container = document.getElementById('guru-flow-view');
    if (!container) return;
    let existing = document.getElementById('gf-sustained-section');
    if (!items || items.length === 0) {
        if (existing) existing.remove();
        return;
    }
    let html = `<div class="glass-panel p-6 rounded-2xl" id="gf-sustained-section">
        <h3 class="text-lg font-semibold text-blue-400 mb-4">🔄 Sustained Buying <span class="text-xs text-gray-500 font-normal">— Bought this quarter AND in 6-month grand portfolio</span></h3>
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left" id="gf-sustained-table">
                <thead class="text-xs text-gray-400 uppercase bg-gray-900/50">
                    <tr>
                        <th class="px-4 py-3 rounded-l-lg" data-sort="symbol">Symbol</th>
                        <th class="px-4 py-3" data-sort="name">Name</th>
                        <th class="px-4 py-3 text-center" data-sort="gurus">Buying Gurus</th>
                        <th class="px-4 py-3 text-center" data-sort="6mo">6mo</th>
                        <th class="px-4 py-3 text-right" data-sort="change">Avg % Chg</th>
                        <th class="px-4 py-3 text-right rounded-r-lg" data-sort="price">Price</th>
                    </tr>
                </thead>
                <tbody id="gf-sustained-body"></tbody>
            </table>
        </div>
    </div>`;
    if (existing) {
        existing.outerHTML = html;
    } else {
        container.insertAdjacentHTML('beforeend', html);
    }
    fillTable('gf-sustained-body', items, a => {
        const pct = a.total_pct_change !== undefined && a.total_pct_change !== null
            ? (a.total_pct_change > 0 ? '+' : '') + a.total_pct_change.toFixed(1) + '%'
            : '';
        return `
        <td class="px-4 py-2.5 font-bold text-white">${linkTV(a.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${a.name || ''}</td>
        <td class="px-4 py-2.5 text-center">${a.manager_count || '0'}</td>
        <td class="px-4 py-2.5 text-center"><span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300">6mo</span></td>
        <td class="px-4 py-2.5 text-right font-mono text-green-400">${pct}</td>
        <td class="px-4 py-2.5 text-right font-mono text-white">${a.current_price || ''}</td>
    `});
    makeSortable('gf-sustained-table');
}

function renderHeavyBets(items) {
    fillTable('gf-heavy-body', items, h => `
        <td class="px-4 py-2.5 font-bold text-white">${linkTV(h.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${h.name || ''}</td>
        <td class="px-4 py-2.5 text-center">${h.ownership_count || '0'}</td>
        <td class="px-4 py-2.5 text-right font-mono text-yellow-400">${h.max_pct || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.portfolio_pct || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono text-white">${h.current_price || ''}</td>
    `);
    makeSortable('gf-heavy-table');
}

function renderNearLow(items) {
    fillTable('gf-near-low-body', items, h => {
        const above = h.above_52w_low_pct || '0';
        const color = parseFloat(above) < 5 ? 'text-red-400' : 'text-yellow-400';
        return `
        <td class="px-4 py-2.5 font-bold text-white">${linkTV(h.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${h.name || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono ${color}">${above}%</td>
        <td class="px-4 py-2.5 text-center">${h.ownership_count || '0'}</td>
        <td class="px-4 py-2.5 text-right font-mono text-gray-400">${h.portfolio_pct || ''}</td>
        <td class="px-4 py-2.5 text-right font-mono text-white">${h.current_price || ''}</td>
    `});
    makeSortable('gf-near-low-table');
}

function renderRotation(items) {
    const container = document.getElementById('guru-flow-view');
    if (!container) return;
    let existing = document.getElementById('gf-rotation-section');
    if (!items || items.length === 0) {
        if (existing) existing.remove();
        return;
    }
    let html = `<div class="glass-panel p-6 rounded-2xl" id="gf-rotation-section">
        <h3 class="text-lg font-semibold text-white mb-4">🔄 Sector Rotation <span class="text-xs text-gray-500 font-normal">— Net manager activity (buying vs selling)</span></h3>
        <div class="overflow-x-auto">
            <table class="w-full text-sm text-left" id="gf-rotation-table">
                <thead class="text-xs text-gray-400 uppercase bg-gray-900/50">
                    <tr>
                        <th class="px-4 py-3 rounded-l-lg" data-sort="symbol">Symbol</th>
                        <th class="px-4 py-3" data-sort="name">Name</th>
                        <th class="px-4 py-3 text-center" data-sort="buying">Buying</th>
                        <th class="px-4 py-3 text-center" data-sort="selling">Selling</th>
                        <th class="px-4 py-3 text-center rounded-r-lg" data-sort="net">Net</th>
                    </tr>
                </thead>
                <tbody id="gf-rotation-body"></tbody>
            </table>
        </div>
    </div>`;
    if (existing) {
        existing.outerHTML = html;
    } else {
        container.insertAdjacentHTML('beforeend', html);
    }
    fillTable('gf-rotation-body', items.slice(0, 20), r => {
        const netClass = r.net_managers > 0 ? 'text-green-400' : 'text-red-400';
        const netLabel = r.net_managers > 0 ? `+${r.net_managers}` : `${r.net_managers}`;
        return `
        <td class="px-4 py-2.5 font-bold text-white">${linkTV(r.symbol || '?')}</td>
        <td class="px-4 py-2.5 text-gray-400 text-xs max-w-[130px] truncate">${r.name || ''}</td>
        <td class="px-4 py-2.5 text-center"><span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-300">${r.buy_managers}</span></td>
        <td class="px-4 py-2.5 text-center"><span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-300">${r.sell_managers}</span></td>
        <td class="px-4 py-2.5 text-center font-mono font-bold ${netClass}">${netLabel}</td>
    `});
    makeSortable('gf-rotation-table');
}
