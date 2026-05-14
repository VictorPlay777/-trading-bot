"""
FeatureSnapshot: freeze the model's feature vector at entry, persist it to disk
with a deterministic content hash.

Why:
- Reproducibility: we can replay any trade exactly as the model saw it
- Model versioning: changes in feature ordering or scaling become detectable
- Post-hoc diagnostics: did 'high confidence + bad features' kill a trade?

Files written under <root>/feature_snapshots/<hash>.json once. The trade row
in trades_v10.jsonl carries only the hash; multiple identical inputs reuse it.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


class FeatureSnapshot:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # In-memory dedupe to avoid hammering disk on repeated identical features.
        self._known_hashes: set[str] = set()

    @staticmethod
    def _canonicalize(features: Dict[str, Any]) -> str:
        """Produce a deterministic JSON string for hashing."""
        # Sort keys; clamp floats to 9-decimal precision to dodge tiny float noise.
        def _round(x: Any) -> Any:
            if isinstance(x, float):
                return round(x, 9)
            if isinstance(x, list):
                return [_round(v) for v in x]
            if isinstance(x, dict):
                return {k: _round(v) for k, v in sorted(x.items())}
            return x

        canonical = _round(features)
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def save(
        self,
        *,
        symbol: str,
        side: str,
        confidence: float,
        score: float,
        features: Dict[str, Any],
        model_version: Optional[str] = None,
        feature_names: Optional[Sequence[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist features to <hash>.json (only once per unique payload).

        Returns the content hash (also used as filename stem).
        """
        canonical = self._canonicalize(features)
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        path = self.root / f"{h}.json"
        with self._lock:
            if h in self._known_hashes or path.exists():
                self._known_hashes.add(h)
                return h
            payload: Dict[str, Any] = {
                "hash": h,
                "ts": time.time(),
                "symbol": symbol,
                "side": side,
                "confidence": float(confidence),
                "score": float(score),
                "model_version": model_version,
                "feature_names": list(feature_names) if feature_names else None,
                "features": features,
            }
            if extra:
                payload["extra"] = extra
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
                self._known_hashes.add(h)
            except Exception:
                # Don't break trading on snapshot failure.
                pass
        return h

    def load(self, h: str) -> Optional[Dict[str, Any]]:
        path = self.root / f"{h}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
