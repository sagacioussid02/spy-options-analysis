# 📚 SPY Trading System - Documentation Index

## Quick Navigation

### 🚀 Getting Started
- **[Quick Start](quick-start/)** - Start here!
  - `QUICK_START_ENHANCED.md` - Fast setup guide
  - `QUICK_COMMANDS.md` - Common commands cheat sheet
  - `QUICK_REFERENCE.md` - API reference

### 📖 Comprehensive Guides
- **[Guides](guides/)** - Deep dives into each system component
  - `QUANTUM_MONTE_CARLO_GUIDE.md` - Quantum options pricing
  - `QUANTUM_PRACTICAL_GUIDE.md` - Practical quantum integration
  - `FINBERT_GUIDE.md` - Sentiment analysis setup
  - `DATABASE_GUIDE.md` - Database operations
  - `EVENT_DRIVEN_GUIDE.md` - Event detection system
  - `OPTIONS_PREMIUM_GUIDE.md` - Options analysis
  - And more...

### 📋 Workflows & Reference
- **[Workflows](workflows/)** - Daily operations and processes
  - `DAILY_WORKFLOW.md` - Morning routine
  - `TOMORROW_WORKFLOW.md` - Planning ahead
  - `TRADE_WORKFLOW.md` - Trading process
  - `SYSTEM_COMPLETE.md` - Full system overview
  - `CHEAT_SHEET.txt` - Quick reference

### 🛠️ Scripts
- **[Scripts](../scripts/)** - Utility scripts
  - `run_analysis.sh` - Run full analysis
  - `setup_free_apis.sh` - Initialize free APIs
  - `test_full_workflow.sh` - Run all tests

### 🧪 Tests
- **[Tests](../tests/)** - Test suites
  - `test_quantum_mc.py` - Quantum Monte Carlo tests

---

## Directory Structure

```
spy/
├── README.md                          # Main documentation
├── docs/
│   ├── INDEX.md                      # You are here
│   ├── guides/                       # Technical guides
│   ├── quick-start/                  # Quick reference
│   └── workflows/                    # Daily operations
├── scripts/                          # Automation scripts
├── tests/                            # Test suites
├── spy_decision_engine/              # Main application
│   ├── main.py                       # Core trading engine
│   ├── config.py
│   ├── database.py
│   ├── engines/                      # Decision engines
│   ├── utils/                        # Utilities & helpers
│   ├── data/                         # Trade database
│   └── reports/                      # Generated reports
└── trade_monitor.py                  # Trade monitoring CLI
```

## Common Tasks

### Running Analysis
```bash
./scripts/run_analysis.sh
```

### Checking Open Trades
```bash
python trade_monitor.py
```

### Setting Up APIs
```bash
./scripts/setup_free_apis.sh
```

### Viewing Dashboard
```bash
python spy_decision_engine/utils/visualize_decision.py
# Then open: spy_decision_engine/reports/dashboard.html
```

## Key Files at Root

| File | Purpose |
|------|---------|
| `README.md` | Main project documentation |
| `trade_monitor.py` | Monitor expiring trades (CLI) |
| `trade_cmd.py` | Trade execution utilities |
| `db_query.py` | Database query utilities |

---

📌 **Tip:** Most documentation is self-contained. Start with guides/ for technical details or workflows/ for step-by-step processes.
