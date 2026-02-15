#!/bin/bash
# Rational Equity - Single Command Launcher

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   📊 Rational Equity - Dashboard${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Virtual Environment (5-10s)
if [ ! -d "venv" ]; then
    echo -e "${CYAN}[1/4]${NC} ${YELLOW}Creating virtual environment...${NC} ${CYAN}(~10s)${NC}"
    python3 -m venv venv
    echo -e "${GREEN}      ✓ Virtual environment ready${NC}\n"
else
    echo -e "${CYAN}[1/4]${NC} ${GREEN}✓ Virtual environment exists${NC}\n"
fi

# Step 2: Activation (instant)
echo -e "${CYAN}[2/4]${NC} ${YELLOW}Activating environment...${NC}"
source venv/bin/activate
echo -e "${GREEN}      ✓ Activated${NC}\n"

# Step 3: Dependencies (smart check - only install if needed)
# Create a checksum file to track requirements.txt changes
REQUIREMENTS_HASH=".requirements.md5"
CURRENT_HASH=$(md5sum requirements.txt | awk '{print $1}')

if [ -f "$REQUIREMENTS_HASH" ]; then
    STORED_HASH=$(cat "$REQUIREMENTS_HASH")
else
    STORED_HASH=""
fi

# Check if we need to install
NEED_INSTALL=false
if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo -e "${CYAN}[3/4]${NC} ${YELLOW}Dependencies changed, updating...${NC} ${CYAN}(~30-60s)${NC}"
    NEED_INSTALL=true
else
    # Quick check: verify key packages are actually installed
    if ! python3 -c "import fastapi, uvicorn, yfinance, pandas" 2>/dev/null; then
        echo -e "${CYAN}[3/4]${NC} ${YELLOW}Missing packages detected, installing...${NC} ${CYAN}(~30-60s)${NC}"
        NEED_INSTALL=true
    else
        echo -e "${CYAN}[3/4]${NC} ${GREEN}✓ Dependencies already installed${NC}"
        NEED_INSTALL=false
    fi
fi

if [ "$NEED_INSTALL" = true ]; then
    echo -e "${BLUE}      ℹ  Showing pip progress below:${NC}\n"
    
    # Upgrade pip first (with progress)
    pip install --upgrade pip 2>&1 | grep -E "(Requirement already satisfied|Successfully installed|Collecting)" || true
    
    # Install requirements with full progress
    echo ""
    pip install -r requirements.txt 2>&1 | while IFS= read -r line; do
        if [[ "$line" =~ "Collecting" ]]; then
            pkg=$(echo "$line" | sed 's/Collecting //' | sed 's/ .*//')
            echo -e "${CYAN}      → Installing:${NC} $pkg"
        elif [[ "$line" =~ "Downloading" ]]; then
            echo -e "${YELLOW}        ⬇${NC}  $line"
        elif [[ "$line" =~ "Successfully installed" ]]; then
            echo -e "${GREEN}      ✓${NC} $line"
        elif [[ "$line" =~ "Requirement already satisfied" ]]; then
            :
        elif [[ "$line" =~ "%" ]]; then
            echo -ne "\r${YELLOW}        Progress:${NC} $line"
        fi
    done
    
    # Save the new hash
    echo "$CURRENT_HASH" > "$REQUIREMENTS_HASH"
    echo -e "\n${GREEN}      ✓ All dependencies ready${NC}\n"
else
    echo -e "${GREEN}      → Skipping installation (everything up to date)${NC}\n"
fi

# Step 4: Environment Setup (instant)
echo -e "${CYAN}[4/4]${NC} ${YELLOW}Checking configuration...${NC}"
if [ ! -f "stockguide/.env" ]; then
    cat > stockguide/.env << 'EOF'
# Add your API keys here if needed
# EXAMPLE_API_KEY=your_key_here
EOF
    echo -e "${GREEN}      ✓ Created .env file${NC}\n"
else
    echo -e "${GREEN}      ✓ Configuration exists${NC}\n"
fi

# Launch
cd stockguide
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🚀 Launching Dashboard...${NC}"
echo -e "${CYAN}   → Server will start on http://localhost:8000${NC}"
echo -e "${CYAN}   → Browser will open automatically${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Run the application
python3 run.py
