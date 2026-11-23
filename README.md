# Monitor — broadcast stream multiviewer

Desktop multiviewer for broadcast operations: watches dozens of live video streams at once, analyses the signal and raises alarms with a probable cause. Built from day-to-day experience in live TV production.

## Features
- **Inputs:** UDP multicast, SRT, RTMP, HTTP and local files (loop playback)
- **Video tiles:** live picture, audio peak level, bitrate per channel; FFmpeg decoding on CPU or GPU (CUDA / NVDEC) with "smooth" and "light" quality modes to reduce load
- **MPEG-TS wire analysis** for multicast inputs: sync-byte errors, null-packet share, continuity-counter (CC) errors and lost-packet count per PID, vectorised with NumPy
- **Picture and audio checks:** black screen, frozen picture, silence, low bitrate, no signal — with hysteresis and raise delays to avoid flapping
- **Alarm diagnosis:** rule-based classifier separates network loss, an encoder sending only null packets, auth errors (401/403/404), SRT handshake failures and group outages across several channels
- **History:** metrics and events stored in SQLite, statistics window with CSV export, alarm log, CPU/GPU usage bar

## Architecture
```
main.py            entry point (Qt application)
core/              Monitor: channel lifecycle, config, events, data models
ingest/pipeline.py one FFmpeg process per channel: video → pipe, audio and TS copy → local TCP;
                   watchdog restarts, reconnect logic
ingest/ts_analyzer.py  multicast receiver + MPEG-TS packet analysis
analyzers/         per-frame picture metrics (brightness, spread, frame difference)
alarms/            alarm engine (thresholds, hysteresis) and cause classifier
storage/           background SQLite writer
ui/                PySide6 widgets: tiles, stream editor, statistics, alarm log, system monitor
```
Every channel runs in its own threads (decode, audio, bitrate, TS analysis); results reach the UI through thread-safe events.

## Requirements
- Python 3.10+
- FFmpeg on `PATH`, or `ffmpeg/ffmpeg.exe` next to the project
- Optional: NVIDIA GPU with CUDA-enabled FFmpeg; `pynvml` for GPU load in the status bar

```
pip install -r requirements.txt
python main.py            # decoder: auto
python main.py cuda       # force GPU decoding
python main.py cpu        # force CPU decoding
```
Channels are stored in `broadcast_config.json` and can be edited from the UI.

## Test tools
| Script | What it does |
|---|---|
| `analyzer.py` | Streams a `.ts` file to several UDP multicast addresses (test sources) |
| `loss_generator.py` | UDP relay that drops a set share of packets, to test CC-error detection |
| `testbench.py` | Benchmarks decoding N streams on CPU vs CUDA: `python testbench.py <url or file> <N> <cpu\|cuda>` |
| `httpcheck.py` | Opens N parallel HTTP-TS connections and counts CC errors: `python httpcheck.py <url> <N> <seconds>` |

`sample.ts` / `real.ts` are sample transport streams; `*_test.json` are ready-made channel sets for load tests.
