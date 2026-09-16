# Spec Delta: prediction-ledger

## ADDED Requirements

### Requirement: Probabilistic predictions from any persona
All personas (bull, bear, pm, futurist, reflect) SHALL have a `log_prediction`
custom tool: {claim (falsifiable, plain english), probability (0.05–0.95),
category: price|macro|industry|stock, horizon_date, basis}. `predictions.py`
SHALL store entries in `predictions.json` tagged with the persona and
debate/thesis id when applicable. Personas SHALL be prompted to log at least one
prediction per session (predictions are free; trades are not).

#### Scenario: Prediction during a debate
- **WHEN** the bull argues SPY strength into month-end
- **THEN** it also logs e.g. {claim: "SPY closes above 625 on 2026-07-31", probability: 0.65, category: "price", ...}

#### Scenario: Vague claims are rejected
- **WHEN** log_prediction is called with a non-falsifiable claim ("market will be volatile-ish")
- **THEN** the tool returns an error asking for a measurable claim with a resolvable horizon

### Requirement: Resolution and Brier scoring
The daily sweep SHALL auto-resolve matured `price` predictions from quote data.
Non-price predictions SHALL be resolved by the weekly reflection agent (with
web_search), each resolution carrying a one-line justification; the human MAY
override any resolution via CLI or web UI. Each resolved prediction SHALL get a
Brier component ((probability - outcome)^2), and `predictions.py` SHALL maintain
per-persona, per-category mean Brier scores with sample counts.

#### Scenario: Auto-resolving a price call
- **WHEN** the sweep runs on/after a price prediction's horizon_date
- **THEN** the prediction is resolved true/false from quotes and its Brier component stored

### Requirement: Calibration feeds the PM
The PM's committee context SHALL include the calibration table (persona x
category, mean Brier, n). Persona prompts SHALL instruct honest probabilities
over confident-sounding ones, noting that their track record is shown to the PM.

#### Scenario: PM discounts a badly calibrated bull
- **WHEN** the bull's price-prediction Brier is materially worse than the bear's over >=10 predictions
- **THEN** the PM context shows it, and the PM prompt directs weighting the better-calibrated persona under disagreement
