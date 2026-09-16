"""
Radar — a store of researched stock candidates (ideas, not orders).

The scout writes candidates here (symbol + sector + the CATALYST that put it on
the radar + a thesis + horizon). It's your idea list / watchlist backing store —
the advisor can later form a sized thesis on any of these, but trading non-SPY
names is a separate, deliberate step (whitelist + funding).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

RADAR_PATH = Path(__file__).parent / "radar.json"


@dataclass
class Candidate:
    id: str
    at: str
    symbol: str
    sector: str
    catalyst_type: str        # policy | geopolitics | investment | insider | other
    catalyst: str             # the news/event that put it on the radar
    thesis: str
    horizon: str              # short | long
    conviction: float         # 0..1
    tradable: Optional[bool] = None
    last_price: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class Radar:
    def __init__(self, path: Path = RADAR_PATH):
        self.path = path

    def _load(self) -> list[dict]:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=2))

    def add(self, **kw) -> Candidate:
        c = Candidate(
            id="rc_" + uuid.uuid4().hex[:10], at=datetime.now(timezone.utc).isoformat(),
            symbol=str(kw.get("symbol", "")).upper(),
            sector=str(kw.get("sector", "")),
            catalyst_type=str(kw.get("catalyst_type", "other")),
            catalyst=str(kw.get("catalyst", "")),
            thesis=str(kw.get("thesis", "")),
            horizon=str(kw.get("horizon", "short")).lower(),
            conviction=max(0.0, min(1.0, float(kw.get("conviction", 0.0) or 0.0))),
            tradable=kw.get("tradable"),
            last_price=kw.get("last_price"),
        )
        # Dedupe by symbol — keep the most recent take.
        items = [i for i in self._load() if i["symbol"] != c.symbol]
        items.append(c.to_dict())
        self._save(items)
        return c

    def list(self) -> list[dict]:
        return self._load()

    def symbols(self) -> list[str]:
        return sorted({i["symbol"] for i in self._load() if i.get("symbol")})

    def by_horizon(self) -> dict:
        out: dict = {"short": [], "long": []}
        for i in sorted(self._load(), key=lambda x: -(x.get("conviction") or 0)):
            out.setdefault(i.get("horizon", "short"), []).append(i)
        return out

    def clear(self) -> None:
        self._save([])


if __name__ == "__main__":
    r = Radar(Path("/tmp/radar_demo.json"))
    r.add(symbol="LMT", sector="Defense/Industrials", catalyst_type="geopolitics",
          catalyst="Escalation raises defense budgets", thesis="Defense primes benefit from sustained spend",
          horizon="long", conviction=0.6)
    r.add(symbol="XOM", sector="Energy", catalyst_type="geopolitics",
          catalyst="Supply risk lifts crude", thesis="Integrated majors gain on higher oil",
          horizon="short", conviction=0.45)
    print(json.dumps(r.by_horizon(), indent=2))
    print("symbols:", r.symbols())
