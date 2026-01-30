# Product Requirements Document (Retrospective)

## 1. Project Overview
**Project Name**: Warren Indicator / Electric Triangulum
**Mission**: To provide retail investors with rational, data-driven market intelligence, stripping away hype to focus on fundamentals, macro trends, and proven superinvestor strategies.

## 2. Problem Statement
Retail investors are often overwhelmed by noise, hype, and short-term volatility. They lack access to:
*   Institutional-grade "Big Picture" metrics (Buffett Indicator, Macro Trends).
*   Contextual valuation (Is "Tech" expensive right now?).
*   Rational analysis frame (Thinking like Buffett, Burry, or Lynch).
*   Live tracking of "Smart Money" (Hedge Fund 13F filings).

## 3. Product Goals
1.  **Macro Context First**: Always show where the overall market stands (Overvalued/Undervalued) before diving into individual stocks.
2.  **Rational Scoring**: Every stock analysis must provide a clear "Score" and "Verdict" based on a specific famous strategy (Buffett, Burry, Lynch).
3.  **Transparency**: No "black box" ratings. Every verdict must be explained with bullet points (e.g., "ROE > 15%").
4.  **Actionable**: Connect insights to actions (e.g., "Deep Value" screener).

## 4. Feature Specifications

### 4.1. The Dashboard (Home)
*   **Buffett Indicator Gauge**: Visual representation of Market Cap / GDP. (Zones: Undervalued, Fair, Overvalued, Bubble).
*   **Macro Trends Ticker**: Live feed of sector tailwinds/headwinds (e.g., "Interest Rates: Headwind for Real Estate").
*   **Industry Valuation Map**: Table showing Sector P/E, Yield, and Quality to identify cheap pockets of the market.
*   **Deep Dive View**: Clicking a sector reveals top "Quality" stocks within it.

### 4.2. Analysis Engine
*   **Strategies**:
    *   *Warren Buffett*: High ROE, Low Debt, Moat, Fair Value.
    *   *Michael Burry*: Deep Value (EV/EBITDA), FCF Yield, Short Candidates.
    *   *Peter Lynch*: GARP (PEG Ratio), Earnings Growth.
*   **Moonshot Mode**: Analysis of speculative/futuristic themes (Robotics, Energy, etc.) with long time horizons (3-10 years).
*   **Output**: "Strong Buy", "Buy", "Hold", "Sell" with specific reasoning.

### 4.3. Superinvestor Radar
*   **13F Tracking**: Monitor top funds (Burry, Buffett, Ackman, Citadel).
*   **Copycat Portfolio**: Aggregated "High Conviction" list (stocks bought by multiple superinvestors).
*   **Visualization**: Cards showing Top Buys, Top Sells, and Portfolio Turnover.

### 4.4. Portfolio Management
*   **CRUD**: Create/Read/Update/Delete multiple portfolios.
*   **Privacy**: Local storage (SQLite), no cloud sync.
*   **Visualization**: Allocation Pie Chart (by Ticker or Strategy).
*   **Currency Support**: Unified view of USD and CAD assets (handling CDRs automatically).

### 4.5. Pro Screeners
*   **Preset Scans**: Magic Formula, Rule of 40, Lynch Growth, Deep Value.
*   **Speed**: In-memory caching for instant results.

## 5. User Personas
*   **The Rationalist**: Wants to verify their intuition with cold hard numbers.
*   **The Learner**: Wants to understand *why* a stock is good (learning from the "Reasons" bullet points).
*   **The Speculator**: Uses the "Moonshots" tab to allocate 5-10% of their portfolio to high-risk bets.

## 6. Technical Constraints
*   **Data Source**: Free APIs only (yfinance, FRED, potentially scraped 13F data).
*   **Architecture**: Lightweight local server (FastAPI) + Vanilla JS frontend.
*   **Privacy**: Zero-knowledge backend preferred (no user data sent to cloud).
