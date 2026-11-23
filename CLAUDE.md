# CLAUDE.md

Broadcast stream multiviewer in Python (PySide6 + FFmpeg + NumPy). See README.md for features.

## Run
- `pip install -r requirements.txt`
- `python main.py [auto|cuda|cpu]` — needs FFmpeg on PATH or in `ffmpeg/`
- Channel config: `broadcast_config.json` (written by the app; keep it valid JSON, written atomically via `.tmp`)

## Layout
- `core/monitor.py` owns channels; `ingest/pipeline.py` builds FFmpeg commands (`build_cmd`) and runs one process per channel
- `ingest/ts_analyzer.py` parses 188-byte TS packets; CC increments only on packets with payload, duplicate (diff 0) is allowed
- `alarms/engine.py` thresholds + hysteresis, `alarms/classifier.py` cause text (rules, not ML)
- `ui/` must only be touched from the Qt main thread — worker threads publish events, they never call widgets directly

## Rules
- Comments and UI strings are in Ukrainian; keep that style
- Threads are daemon threads stopped via `threading.Event`; every new worker must stop in `Monitor.stop()`
- Always kill the whole FFmpeg process tree (`_kill_tree`) — orphaned FFmpeg processes are the most common leak
- Test against `sample.ts` with `tstest_config.json` / `light_test.json` / `smooth_test.json` before changing the pipeline; use `loss_generator.py` to verify CC counting
