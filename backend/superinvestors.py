def get_superinvestors():
    return [
        {
            "id": "burry",
            "name": "Michael Burry",
            "firm": "Scion Asset Management",
            "style": "Deep Value / Contrarian",
            "image": "https://upload.wikimedia.org/wikipedia/en/4/44/Michael_Burry.jpg",
            "history": [
                {
                    "quarter": "Q3 2025",
                    "summary": "Full reversal to Bearish. Liquidated Q2 positions. Loaded up on Puts against AI bubble.",
                    "top_buys": [
                        {"symbol": "NVDA", "name": "Nvidia (PUTS)", "change": "NEW"},
                        {"symbol": "PLTR", "name": "Palantir (PUTS)", "change": "NEW"},
                        {"symbol": "MOH", "name": "Molina Healthcare", "change": "NEW"}
                    ],
                    "top_sells": [
                        {"symbol": "UNH", "name": "UnitedHealth", "change": "EXIT"},
                        {"symbol": "REGN", "name": "Regeneron", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "AI Puts (NVDA/PLTR)",
                        "type": "MACRO SHORT",
                        "description": "Massive bearish bet (>79% of reported assets) against the 'AI Hype' sector."
                    }
                },
                {
                    "quarter": "Q2 2025",
                    "summary": "Brief 'Risk-On' phase. Bought Healthcare and Chinese Tech.",
                    "top_buys": [
                        {"symbol": "UNH", "name": "UnitedHealth", "change": "NEW"},
                        {"symbol": "REGN", "name": "Regeneron", "change": "NEW"},
                        {"symbol": "BABA", "name": "Alibaba", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "JD", "name": "JD.com", "change": "REDUCED"},
                        {"symbol": "PHYS", "name": "Gold Trust", "change": "TRIMMED"}
                    ],
                    "weirdest_bet": {
                        "symbol": "Chinese Tech",
                        "type": "VALUE",
                        "description": "Contrarian value play in a beaten-down sector."
                    }
                },
                {
                    "quarter": "Q1 2025",
                    "summary": "Estée Lauder was the only stock holding. High cash pile.",
                    "top_buys": [
                        {"symbol": "EL", "name": "Estée Lauder", "change": "DOUBLED DOWN"}
                    ],
                    "top_sells": [
                        {"symbol": "GOOGL", "name": "Alphabet", "change": "EXIT"},
                        {"symbol": "AMZN", "name": "Amazon", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "EL",
                        "type": "DEEP VALUE",
                        "description": "holding ONLY Estée Lauder? A hyper-concentrated bet on a luxury turnaround."
                    }
                }
            ]
        },
        {
            "id": "buffett",
            "name": "Warren Buffett",
            "firm": "Berkshire Hathaway",
            "style": "Quality / Long Term",
            "history": [
                {
                    "quarter": "Q3 2025",
                    "summary": "Surprise entry into Alphabet (GOOGL) and Domino's. Trimming Apple further.",
                    "top_buys": [
                        {"symbol": "GOOGL", "name": "Alphabet", "change": "NEW"},
                        {"symbol": "DPZ", "name": "Domino's Pizza", "change": "NEW"},
                        {"symbol": "CB", "name": "Chubb Ltd", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "AAPL", "name": "Apple", "change": "REDUCED"},
                        {"symbol": "BAC", "name": "Bank of America", "change": "REDUCED"},
                        {"symbol": "BYD", "name": "BYD Co", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "GOOGL",
                        "type": "TECH VALUE",
                        "description": "Buffett finally buying Google? Likely a valuation play by his lieutenants."
                    }
                },
                {
                    "quarter": "Q2 2025",
                    "summary": "Defensive Posture. Selling T-Mobile, Buying Energy & Builders.",
                    "top_buys": [
                        {"symbol": "CVX", "name": "Chevron", "change": "ADDED"},
                        {"symbol": "STZ", "name": "Constellation Brands", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "TMUS", "name": "T-Mobile", "change": "EXIT"},
                        {"symbol": "DVA", "name": "DaVita", "change": "REDUCED"}
                    ],
                    "weirdest_bet": {
                        "symbol": "Homebuilders",
                        "type": "SECTOR",
                        "description": "Continued confidence in US Housing despite rate uncertainty."
                    }
                },
                {
                    "quarter": "Q1 2025",
                    "summary": "Selling Banks (Citi) and buying Insurance/Energy.",
                    "top_buys": [
                        {"symbol": "CB", "name": "Chubb Ltd", "change": "NEW"}
                    ],
                    "top_sells": [
                        {"symbol": "C", "name": "Citigroup", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "Cash Pile",
                        "type": "MACRO",
                        "description": "Record cash reserves indicate a lack of 'fat pitch' opportunities."
                    }
                }
            ]
        },
        {
            "id": "druckenmiller",
            "name": "Stanley Druckenmiller",
            "firm": "Duquesne Family Office",
            "style": "Macro / Trend",
            "history": [
                {
                    "quarter": "Q3 2025",
                    "summary": "Agile Repositioning. Sold Microsoft/Lilly, Bought Amazon/Emerging Markets.",
                    "top_buys": [
                        {"symbol": "AMZN", "name": "Amazon", "change": "NEW"},
                        {"symbol": "EEM", "name": "Emerging Mkts ETF", "change": "NEW"},
                        {"symbol": "META", "name": "Meta Platforms", "change": "NEW"}
                    ],
                    "top_sells": [
                        {"symbol": "MSFT", "name": "Microsoft", "change": "EXIT"},
                        {"symbol": "LLY", "name": "Eli Lilly", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "EEM",
                        "type": "MACRO",
                        "description": "Betting on Emerging Markets when the dollar is strong? Typical contrarian macro play."
                    }
                },
                {
                    "quarter": "Q2 2025",
                    "summary": "Bullish Tech & Financials. Bought Microsoft & Sea Ltd.",
                    "top_buys": [
                        {"symbol": "MSFT", "name": "Microsoft", "change": "NEW"},
                        {"symbol": "SE", "name": "Sea Ltd", "change": "NEW"},
                        {"symbol": "C", "name": "Citigroup", "change": "NEW"}
                    ],
                    "top_sells": [
                        {"symbol": "NTRA", "name": "Natera", "change": "TRIMMED"},
                        {"symbol": "WWD", "name": "Woodward", "change": "TRIMMED"}
                    ],
                    "weirdest_bet": {
                        "symbol": "Citigroup",
                        "type": "VALUE",
                        "description": "Buying a turnaround bank while others (Buffett) are selling/holding."
                    }
                },
                {
                    "quarter": "Q1 2025",
                    "summary": "Exited Nvidia early. Shifted to 'AI Adopters' over 'AI Hardware'.",
                    "top_buys": [
                        {"symbol": "NTRA", "name": "Natera", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "NVDA", "name": "Nvidia", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "Selling NVDA",
                        "type": "TIMING",
                        "description": "Sold the biggest winner of the decade early, fearing overhype."
                    }
                }
            ]
        },
        {
            "id": "pabrai",
            "name": "Mohnish Pabrai",
            "firm": "Dalal Street LLC",
            "style": "Cloner / Deep Value",
            "history": [
                 {
                    "quarter": "Q3 2025",
                    "summary": "The 'Offshore Drilling' Super-Bet. massive entry into Transocean (RIG) while dumping AutoNation.",
                    "top_buys": [
                        {"symbol": "RIG", "name": "Transocean", "change": "NEW (22%)"},
                        {"symbol": "AMR", "name": "Alpha Met. Coal", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "AN", "name": "AutoNation", "change": "EXIT"},
                        {"symbol": "NE", "name": "Noble Corp", "change": "SLASHED"}
                    ],
                    "weirdest_bet": {
                        "symbol": "RIG",
                        "type": "DEEP DISTRESS",
                        "description": "Investing 22% of portfolio into an offshore driller? Suggests a multi-year bull cycle thesis for oil services."
                    }
                },
                {
                    "quarter": "Q2 2025",
                    "summary": "Accumulation phase. Adding to Energy and Auto Retail.",
                    "top_buys": [
                        {"symbol": "AN", "name": "AutoNation", "change": "NEW"},
                        {"symbol": "VAL", "name": "Valaris", "change": "ADDED"}
                    ],
                    "top_sells": [
                        {"symbol": "None", "name": "No Major Exits", "change": "--"}
                    ],
                    "weirdest_bet": {
                        "symbol": "VAL",
                        "type": "OFFSHORE",
                        "description": "Building position in offshore drillers before the market wakes up to the supply shortage."
                    }
                },
                {
                    "quarter": "Q1 2025",
                    "summary": "High Conviction in Coal & Steel. Ignoring ESG narratives.",
                    "top_buys": [
                        {"symbol": "AMR", "name": "Alpha Met. Coal", "change": "AGGRESSIVE BUY"}
                    ],
                    "top_sells": [
                        {"symbol": "MU", "name": "Micron", "change": "EXIT"}
                    ],
                    "weirdest_bet": {
                        "symbol": "AMR",
                        "type": "ANTI-ESG",
                        "description": "Betting on metallurgical coal for steel production. A pure play on infrastructure demand."
                    }
                }
            ]
        }
    ]
