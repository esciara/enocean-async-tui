from __future__ import annotations

import json
from importlib.resources import files


def test_fixture_contents() -> None:
    path = files("enocean_async_tui.fixtures").joinpath("burst-300.jsonl")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    rorg_bytes = {bytes.fromhex(r["telegram_hex"])[0] for r in records}
    sender_ids = {bytes.fromhex(r["telegram_hex"])[-5:-1] for r in records}

    assert len(rorg_bytes) >= 2, f"expected ≥2 distinct RORG bytes, got {rorg_bytes!r}"
    assert len(sender_ids) >= 2, f"expected ≥2 distinct sender IDs, got {len(sender_ids)}"
