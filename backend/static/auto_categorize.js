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
    if (t.match(/^(AAPL|MSFT|GOOGL|GOOG|AMZN|NVDA|TSLA|META|NFLX|AMD|CRM|ADBE|PLTR|RIVN|NIO|MVIS|CRSP|AIEQ)$/)) return 'Growth';

    // Value stocks (established, dividend-paying)
    if (t.match(/^(BRK\.B|JPM|JNJ|PG|KO|PEP|WMT|HD|UNH|V|MA|DIS|MCD|NKE|CMCSA|PFE|VZ|T|CLX)$/)) return 'Value';

    // Canadian banks/utilities
    if (t.match(/^(TD|BNS|RY|BMO|CM|ENB|TRP|SU|CNQ|AQN|AC|RCI)$/)) return 'Value';

    // Default
    return 'Stock';
}
