// frontend/app.js - Main Orchestrator

import { API_BASE } from './js/api.js';
import { loadMarketStatus, loadMacroTrends } from './js/components/marketStatus.js';
import { loadIndustries, loadStocks, searchStock, startResearch, loadResearch, loadTrends, loadPriceChart } from './js/components/researchUi.js';
import { loadTechnicalZones } from './js/components/technicalZones.js';
import { loadSuperinvestors, loadCopycatPortfolio, loadMoonshots, loadGuruConsensus, openSuperinvestorDetail, closeSuperinvestorDetail } from './js/components/thematic.js';
import { loadGuruFlow } from './js/components/guruFlow.js';
import { runScreen } from './js/components/screenerUi.js';
import { loadEconomicIndicators, loadMoneyFlow, loadMarketNews, loadContrarianOpportunities, filterContrarian } from './js/components/economics.js';
import { loadDipHunterData, sortDipStocks } from './js/components/dipHunter.js';
import { loadAlphaIntelligence } from './js/components/alpha.js';
import { loadSmallCaps } from './js/components/smallCaps.js';
import { initInternational } from './js/components/international.js';
import { loadMomentumData } from './js/components/momentum.js';

// --- Theme Management ---
function toggleThemeMenu() {
    const menu = document.getElementById('theme-menu');
    if (!menu) return;
    menu.classList.toggle('hidden');

    const closeMenu = (e) => {
        const container = document.getElementById('theme-switcher-container');
        if (container && !container.contains(e.target)) {
            menu.classList.add('hidden');
            document.removeEventListener('click', closeMenu);
        }
    };
    if (!menu.classList.contains('hidden')) {
        setTimeout(() => document.addEventListener('click', closeMenu), 10);
    }
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('selected-theme', theme);
    const iconEl = document.getElementById('current-theme-icon');
    const iconMap = { 'dark': '🌙', 'light': '☀️', 'solaris': '🌅', 'contrast': '👁️' };
    if (iconEl) iconEl.textContent = iconMap[theme] || '🌙';
    const menu = document.getElementById('theme-menu');
    if (menu) menu.classList.add('hidden');
}

function initTheme() {
    const saved = localStorage.getItem('selected-theme') || 'dark';
    setTheme(saved);
}

// --- Universe Badge ---
function renderUniverseBadge(meta, forceMode) {
    if (forceMode === 'curated') {
        return `<span class="universe-badge universe-badge--curated" title="Universe is curated by hand">📌 Curated</span>`;
    }
    if (!meta) return '';
    const isDynamic = meta.is_dynamic;
    const isPartial = meta.partially_dynamic;
    const scoredAt = meta.scored_at ? new Date(meta.scored_at).toLocaleDateString() : null;

    if (isDynamic) {
        const tip = scoredAt ? `Live-ranked with financial metrics · Scored ${scoredAt} · Refreshes every 24h` : 'Live-ranked with financial metrics · Refreshes every 24h';
        return `<span class="universe-badge universe-badge--live" title="${tip}">⚡ Live Universe</span>`;
    } else if (isPartial) {
        return `<span class="universe-badge universe-badge--partial" title="Some sectors using live ranking, others using curated fallback">⚡ Partially Live</span>`;
    } else {
        return `<span class="universe-badge universe-badge--static" title="Using curated fallback list">📌 Static Universe</span>`;
    }
}

(function injectBadgeCSS() {
    if (document.getElementById('universe-badge-style')) return;
    const style = document.createElement('style');
    style.id = 'universe-badge-style';
    style.textContent = `
        .universe-badge {
            display: inline-flex; align-items: center; gap: 4px;
            font-size: 10px; font-weight: 700; letter-spacing: 0.05em;
            text-transform: uppercase; padding: 2px 8px; border-radius: 9999px;
            cursor: default; transition: opacity 0.2s;
        }
        .universe-badge:hover { opacity: 0.85; }
        .universe-badge--live   { background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }
        .universe-badge--partial { background: rgba(250,204,21,0.15); color: #facc15; border: 1px solid rgba(250,204,21,0.3); }
        .universe-badge--static { background: rgba(251,146,60,0.15); color: #fb923c; border: 1px solid rgba(251,146,60,0.3); }
        .universe-badge--curated { background: rgba(139,92,246,0.15); color: #a78bfa; border: 1px solid rgba(139,92,246,0.3); }
    `;
    document.head.appendChild(style);
})();

// --- Window Bindings for HTML ---
// HTML components call these functions via inline \`onclick\` handlers.
window.searchStock = searchStock;
window.startResearch = startResearch;
window.loadResearch = loadResearch;
window.loadStocks = loadStocks;
window.runScreen = runScreen;
window.filterContrarian = filterContrarian;
window.sortDipStocks = sortDipStocks;
window.toggleThemeMenu = toggleThemeMenu;
window.setTheme = setTheme;
window.renderUniverseBadge = renderUniverseBadge;
window.loadTrends = loadTrends;
window.loadPriceChart = loadPriceChart;
window.loadTechnicalZones = loadTechnicalZones;
window.loadCopycatPortfolio = loadCopycatPortfolio;
window.loadGuruConsensus = loadGuruConsensus;
window.loadGuruFlow = loadGuruFlow;
window.openSuperinvestorDetail = openSuperinvestorDetail;
window.closeSuperinvestorDetail = closeSuperinvestorDetail;
window.closeModal = () => document.getElementById('forecast-modal').classList.add('hidden');

// --- Tab Navigation Orchestrator ---
function switchTab(tabName) {
    const tabs = ['dashboard', 'superinvestors', 'copycat', 'moonshots', 'screeners', 'economics', 'diphunter', 'contrarian', 'momentum', 'alpha', 'small-caps', 'international', 'portfolio', 'technical-zones', 'research', 'guru-flow'];

    tabs.forEach(t => {
        const btn = document.getElementById(`tab-${t}`);
        const view = document.getElementById(`${t}-view`);

        if (btn) {
            btn.classList.remove('bg-warren-accent', 'text-white', 'shadow-lg');
            btn.classList.add('text-gray-400');
        }
        if (view) view.classList.add('hidden');
    });

    const activeBtn = document.getElementById(`tab-${tabName}`);
    const activeView = document.getElementById(`${tabName}-view`);

    if (activeBtn) {
        activeBtn.classList.add('bg-warren-accent', 'text-white', 'shadow-lg');
        activeBtn.classList.remove('text-gray-400');
    }
    if (activeView) activeView.classList.remove('hidden');

    if (tabName === 'superinvestors') {
        loadSuperinvestors();
        loadGuruConsensus('grand_portfolio');
    } else if (tabName === 'guru-flow') loadGuruFlow();
    else if (tabName === 'copycat') loadCopycatPortfolio('all');
    else if (tabName === 'moonshots') loadMoonshots();
    else if (tabName === 'economics') {
        loadEconomicIndicators();
        loadMoneyFlow();
        loadMarketNews();
    }
    else if (tabName === 'contrarian') loadContrarianOpportunities();
    else if (tabName === 'momentum') loadMomentumData();
    else if (tabName === 'diphunter') loadDipHunterData();
    else if (tabName === 'alpha') loadAlphaIntelligence();
    else if (tabName === 'small-caps') loadSmallCaps();
    else if (tabName === 'technical-zones') loadTechnicalZones();
    else if (tabName === 'international') initInternational();
    else if (tabName === 'portfolio' && typeof window.initPortfolioView === 'function') {
        window.initPortfolioView();
    }
}
window.switchTab = switchTab;

// --- Data Source Toggle ---
async function loadDataSourceStatus() {
    try {
        const res = await fetch(`${API_BASE}/admin/data-source`);
        const data = await res.json();
        updateDataSourceUI(data);
    } catch (e) {
        console.error("Failed to load data source status:", e);
    }
}

function updateDataSourceUI(data) {
    const btn = document.getElementById('datasource-toggle');
    const label = document.getElementById('datasource-label');
    if (!btn || !label) return;

    label.textContent = data.current_source;

    if (data.defeatbeta_enabled) {
        btn.className = "px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border transition-all bg-purple-500/20 text-purple-300 border-purple-500/50 hover:bg-purple-500/30";
    } else {
        btn.className = "px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border transition-all bg-blue-500/20 text-blue-300 border-blue-500/50 hover:bg-blue-500/30";
    }
}

async function toggleDataSource() {
    const btn = document.getElementById('datasource-toggle');
    const label = document.getElementById('datasource-label');
    if (!label) return;

    const currentlyDefeatbeta = label.textContent === 'defeatbeta';
    const newState = !currentlyDefeatbeta;
    const sourceName = newState ? 'yfinance' : 'defeatbeta';

    // Optimistic UI update
    label.textContent = 'Switching...';
    btn.classList.add('animate-pulse');

    try {
        const res = await fetch(`${API_BASE}/admin/data-source`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: newState })
        });
        const data = await res.json();

        updateDataSourceUI({
            defeatbeta_enabled: newState,
            current_source: data.current || sourceName
        });
        btn.classList.remove('animate-pulse');

        // Show reload prompt
        const reload = confirm(data.message + '\n\nReload now?');
        if (reload) {
            window.location.reload();
        }
    } catch (e) {
        label.textContent = sourceName;
        btn.classList.remove('animate-pulse');
        alert('Failed to switch data source: ' + e.message);
    }
}
window.toggleDataSource = toggleDataSource;

// --- Init Event ---
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    // Fire independent loads in parallel — no blocking
    Promise.allSettled([
        loadMarketStatus(),
        loadMacroTrends(),
        loadIndustries(),
        loadDataSourceStatus(),
    ]);
});
