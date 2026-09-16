# Spec Delta: futurist-research

## ADDED Requirements

### Requirement: Long-horizon thesis writing
`cma_lab/futurist.py` SHALL run a hosted "Futurist" persona (web_search,
web_fetch, Robinhood read tools, radar read, log_prediction, and a
`write_thesis` custom tool) on a monthly schedule and on demand. Each run
produces or updates `cma_lab/theses/<slug>.md`: a 3–12 month view on an industry
or single name — where the industry is heading, winners/losers, catalysts,
timeline — ending with 2–4 falsifiable predictions logged to the prediction
ledger (category industry|stock) and a "what would change my mind" section.

#### Scenario: New industry thesis
- **WHEN** the futurist researches, e.g., the power/datacenter buildout
- **THEN** theses/power-datacenter.md is written with the required sections, and its predictions appear in predictions.json tagged persona "futurist"

### Requirement: Thesis review against its own predictions
Each monthly run SHALL begin by reviewing all existing theses: check its
resolved/pending predictions and recent news, then mark each thesis
`strengthening | intact | weakening | invalidated` with a dated note appended.
Invalidated theses move to `theses/archive/` (kept for learning).

#### Scenario: Thesis weakens
- **WHEN** two of a thesis's predictions resolved false
- **THEN** the review marks it `weakening` with a dated explanation, and the next committee sessions see the downgraded status

### Requirement: Theses feed the committee and radar
Bull, bear, and PM contexts SHALL include a compact theses index (slug, one-line
view, status, next catalyst). Radar scout SHALL receive the index so short-term
catalyst hunting can connect to long-term views. Trading remains bound by the
risk_gate whitelist — theses inform the SPY macro view and build research
capability; widening the tradable universe is a separate future change.

#### Scenario: Thesis informs a SPY debate
- **WHEN** a `strengthening` thesis implies index-level tailwinds (e.g., cap-ex supercycle)
- **THEN** the bull can cite it by slug in its case and the debate record preserves the citation
