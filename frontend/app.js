// frontend/app.js - Main Orchestrator

import { API_BASE } from './js/api.js';
import { loadMarketStatus, loadMacroTrends } from './js/components/marketStatus.js';
import { loadIndustries, loadStocks, searchStock, startResearch, loadResearch } from './js/components/researchUi.js';
import { loadSuperinvestors, loadCopycatPortfolio, loadMoonshots } from './js/components/thematic.js';
import { runScreen } from './js/components/screenerUi.js';
import { loadEconomicIndicators, loadMoneyFlow, loadMarketNews, loadContrarianOpportunities, filterContrarian } from './js/components/economics.js';
import { loadDipHunterData, sortDipStocks } from './js/components/dipHunter.js';
import { loadAlphaIntelligence } from './js/components/alpha.js';
import { loadSmallCaps } from './js/components/smallCaps.js';
import { initInternational } from './js/components/international.js';

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
window.closeModal = () => document.getElementById('forecast-modal').classList.add('hidden');

// --- Tab Navigation Orchestrator ---
function switchTab(tabName) {
    const tabs = ['dashboard', 'superinvestors', 'copycat', 'moonshots', 'screeners', 'economics', 'contrarian', 'diphunter', 'alpha', 'small-caps', 'international', 'portfolio', 'research'];

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

    if (tabName === 'superinvestors') loadSuperinvestors();
    else if (tabName === 'copycat') loadCopycatPortfolio();
    else if (tabName === 'moonshots') loadMoonshots();
    else if (tabName === 'economics') {
        loadEconomicIndicators();
        loadMoneyFlow();
        loadMarketNews();
    }
    else if (tabName === 'contrarian') loadContrarianOpportunities();
    else if (tabName === 'diphunter') loadDipHunterData();
    else if (tabName === 'alpha') loadAlphaIntelligence();
    else if (tabName === 'small-caps') loadSmallCaps();
    else if (tabName === 'international') initInternational();
    else if (tabName === 'portfolio' && typeof window.initPortfolioView === 'function') {
        window.initPortfolioView();
    }
}
window.switchTab = switchTab;

// --- Init Event ---
document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await loadMarketStatus();
    await loadMacroTrends();
    await loadIndustries();
});
