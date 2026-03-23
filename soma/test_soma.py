"""
SOMA smoke test — creates a temporary database, writes sample data, reads it back,
checks freshness, then cleans up.
"""

import os
import tempfile
import json
from pathlib import Path
from soma_bridge import SomaBridge


def main() -> None:
    # Use a temp file so we don't pollute the real data directory
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    print("=== SOMA Smoke Test ===\n")

    with SomaBridge(db_path=tmp_path) as db:
        # 1. Initialize
        db.initialize_db()
        ver = db.get_schema_version()
        print(f"[OK] Schema initialized — version: {ver}")

        # 2. Write a regime entry
        db.write_regime(
            date="2026-03-20",
            run_id="test-run-001",
            gli_value=0.72,
            regime="RISK_ON",
            diffusion_index=0.85,
            momentum=0.14,
            gli_components_json=json.dumps({"copper": 1.2, "pmi": 53.1}),
            module_version="test-v0.1",
        )
        print("[OK] Wrote regime entry")

        # 3. Write a valuation entry
        db.write_valuation(
            date="2026-03-20",
            run_id="test-run-001",
            ticker="MSTR",
            fair_value=420.00,
            current_price=385.50,
            implied_upside=0.089,
            execution_score=7.5,
            module_version="test-v0.1",
        )
        print("[OK] Wrote valuation entry")

        # 4. Read them back
        regime = db.get_latest_regime()
        print(f"\n--- Latest Regime ---")
        print(f"  Date:       {regime['date']}")
        print(f"  Regime:     {regime['regime']}")
        print(f"  GLI:        {regime['gli_value']}")
        print(f"  Diffusion:  {regime['diffusion_index']}")
        print(f"  Momentum:   {regime['momentum']}")

        vals = db.get_latest_valuations()
        print(f"\n--- Latest Valuations ({len(vals)} ticker(s)) ---")
        for v in vals:
            print(f"  {v['ticker']}: fair={v['fair_value']}, price={v['current_price']}, upside={v['implied_upside']}")

        # 5. Check freshness
        fresh, age_hrs = db.is_fresh("regime_history", max_age_hours=48)
        print(f"\n--- Freshness Check ---")
        print(f"  regime_history fresh (<48h): {fresh}  (age: {age_hrs}h)")

        # 6. Verify schema version (5 migrations: initial + events + kb_rules + client_profiles + kb_violations)
        assert ver == 5, f"Expected schema version 5, got {ver}"
        assert regime["regime"] == "RISK_ON"
        assert len(vals) == 1
        assert fresh is True
        print("\n[OK] All assertions passed!")

    # Cleanup — use pathlib for better path handling
    tmp_p = Path(tmp_path)
    try:
        tmp_p.unlink()
    except FileNotFoundError:
        pass
    # WAL/SHM files may also exist
    for suffix in ["-wal", "-shm"]:
        try:
            (tmp_p.parent / (tmp_p.name + suffix)).unlink()
        except FileNotFoundError:
            pass
    print(f"[OK] Cleaned up temp database\n")
    print("=== SOMA is operational. ===")


if __name__ == "__main__":
    main()
