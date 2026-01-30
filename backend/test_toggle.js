// Test the toggle logic in isolation
// This simulates the JavaScript behavior

// Simulate the initial state
let currentRefreshedPositions = [];
let allocationMode = 'ticker';

console.log('=== Test 1: Empty array check ===');
console.log('currentRefreshedPositions:', currentRefreshedPositions);
console.log('!currentRefreshedPositions:', !currentRefreshedPositions);
console.log('currentRefreshedPositions.length:', currentRefreshedPositions.length);
console.log('currentRefreshedPositions.length === 0:', currentRefreshedPositions.length === 0);

// Old broken check
if (!currentRefreshedPositions) {
    console.log('OLD CHECK: Would return early (WRONG - this never happens!)');
} else {
    console.log('OLD CHECK: Would NOT return early (CORRECT but for wrong reason)');
}

// New fixed check
if (!currentRefreshedPositions || currentRefreshedPositions.length === 0) {
    console.log('NEW CHECK: Would return early (CORRECT - array is empty)');
} else {
    console.log('NEW CHECK: Would NOT return early');
}

console.log('\n=== Test 2: Array with data ===');
currentRefreshedPositions = [
    { ticker: 'AAPL', value: 1000, category: 'Growth' },
    { ticker: 'MSFT', value: 2000, category: 'Growth' },
    { ticker: 'BRK-B', value: 1500, category: 'Value' }
];

console.log('currentRefreshedPositions.length:', currentRefreshedPositions.length);

// Old check
if (!currentRefreshedPositions) {
    console.log('OLD CHECK: Would return early');
} else {
    console.log('OLD CHECK: Would NOT return early (CORRECT)');
}

// New check
if (!currentRefreshedPositions || currentRefreshedPositions.length === 0) {
    console.log('NEW CHECK: Would return early');
} else {
    console.log('NEW CHECK: Would NOT return early (CORRECT)');
}

console.log('\n=== Test 3: Toggle functionality ===');
console.log('Initial mode:', allocationMode);

// Simulate toggle
allocationMode = allocationMode === 'ticker' ? 'category' : 'ticker';
console.log('After toggle:', allocationMode);

allocationMode = allocationMode === 'ticker' ? 'category' : 'ticker';
console.log('After second toggle:', allocationMode);

console.log('\n=== Test 4: Category grouping ===');
const categories = {};
currentRefreshedPositions.forEach(p => {
    const cat = p.category || 'Stock';
    categories[cat] = (categories[cat] || 0) + p.value;
});

console.log('Grouped by category:', categories);
console.log('Expected: { Growth: 3000, Value: 1500 }');
