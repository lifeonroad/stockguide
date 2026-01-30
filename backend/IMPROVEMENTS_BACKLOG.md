# UI/UX Improvements Backlog

Quick wins and polish items to implement between major features.

---

## 🎯 Priority Improvements

### 1. Sector Deep Dive - Industry Benchmarks in Headers
**Status**: Pending  
**Effort**: Small (1-2 hours)

**Current State**:
```
Stock    Price    P/E    ROE %    Debt/Eq    Margin %
AAPL     $185     28.5   45.2     1.2        25.3
```

**Desired State**:
```
Stock    Price    P/E           ROE %         Debt/Eq       Margin %
                  (Avg: 22.3)   (Avg: 18.5)   (Avg: 0.8)    (Avg: 15.2)
AAPL     $185     28.5          45.2          1.2           25.3
         ↑ Above Avg            ↑ Strong      ↑ Higher      ↑ Strong
```

**Implementation**:
- Calculate industry average for each metric when loading sector
- Display in column header with subtle styling
- Optional: Color-code cells (green if better than avg, red if worse)
- Add tooltip: "Industry Average: 22.3 | Best in Sector: 15.2 (MSFT)"

**Files to Edit**:
- `backend/screener.py`: Add `calculate_sector_averages()` function
- `frontend/app.js`: Update `renderSectorTable()` to show averages in headers
- `frontend/index.html`: Add header row styling for averages

---

## 📋 Future Quick Wins

### 2. TradingView Link Fix
**Status**: In Progress (debugging)  
**Issue**: Modal links showing AAPL for all stocks  
**Solution**: Verify JavaScript update timing

### 3. Export Portfolio to CSV
**Status**: Planned  
**Effort**: Small  
**Benefit**: Users can import to Excel/Google Sheets

### 4. Dark/Light Theme Toggle
**Status**: Idea  
**Effort**: Medium  
**Benefit**: Accessibility improvement

### 5. Keyboard Shortcuts
**Status**: Idea  
**Effort**: Small  
**Examples**:
- `/` - Focus search bar
- `Esc` - Close modal
- `1-5` - Switch tabs

### 6. Loading Skeletons
**Status**: Idea  
**Effort**: Small  
**Benefit**: Better perceived performance

### 7. Mobile Responsive Layout
**Status**: Idea  
**Effort**: Large  
**Benefit**: Use on tablets/phones

---

## 🐛 Bug Fixes

### TradingView Link Issue
- [ ] Verify `modal-tradingview-link` element exists
- [ ] Check console for update logs
- [ ] Test with hard refresh

---

## 📝 Notes

- Keep improvements focused on user value
- Test each change thoroughly
- Update this file as items are completed
- Mark completed items with ✅
