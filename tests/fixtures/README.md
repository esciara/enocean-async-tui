# Dongle test fixtures

JSONL recordings replayed by `FakeDongle`. One JSON object per line:

```jsonc
{
  "t_offset_ms": 0,             // int, ms since recording start (monotonic)
  "telegram_hex": "f6100123...", // hex-encoded raw ERP1 frame: rorg(1) + payload + sender(4) + status(1)
  "rssi_dbm": -65,              // int | null, optional; null => upstream "unknown" (0xFF)
  "comment": "..."              // optional, ignored at runtime
}
```

## Files

| File | Purpose |
|---|---|
| `recordings/single-rps.jsonl` | Single RPS frame; proves the callback → queue → iterator path. |
| `recordings/burst-300.jsonl` | 300 RPS frames; drives the queue-overflow test (300 > 256 default). |

## Regeneration

A `scripts/record_dongle.py` will land when needed (Phase 1+). For Phase 0 the
two files above are hand-generated — see commit history.
