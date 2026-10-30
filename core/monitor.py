import threading
import time

from alarms.engine import AlarmEngine
from alarms.logger import FileAlarmLogger
from alarms.classifier import Classifier
from core.config import (CONFIG_FILE, DEFAULT_THRESHOLDS, ROOT,
                         load_config, save_config)
from core.events import EventBus
from core.models import ChannelState
from ingest.pipeline import ChannelPipeline
from storage.db import Storage


class Channel:
    def __init__(self, cid, cfg, state):
        self.cid, self.cfg, self.state = cid, cfg, state
        self.pipeline = None
        self.boosted = False


class Monitor:
    """Оркестратор: канали, пайплайни, шина подій, алярми, сховище."""

    def __init__(self, config_path=CONFIG_FILE, decoder="auto"):
        self.config_path = config_path
        self.decoder = decoder
        streams, defaults = load_config(config_path)
        self.defaults = {**DEFAULT_THRESHOLDS, **defaults}
        self.bus = EventBus()
        self.engine = AlarmEngine(self.bus.publish, Classifier().classify)
        self.storage = Storage(ROOT / "monitor.db")
        self.logger = FileAlarmLogger(self.bus)
        self.bus.subscribe("alarm", None, lambda cid, ev: self.storage.add_event(ev))
        self.channels = {}
        self._next = 1
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._running = False
        for s in streams:
            self._create(dict(s))

    # ── доступ для UI ────────────────────────────────────────────────────────
    def channel_ids(self):
        return list(self.channels)

    def get_state(self, cid):
        return self.channels[cid].state

    def active_alarms(self, cid):
        return self.engine.active(cid)

    # ── керування каналами (можна викликати на ходу) ─────────────────────────
    def add_channel(self, cfg):
        with self._lock:
            ch = self._create(dict(cfg))
            self.bus.publish("channels", ch.cid, "added")
            if self._running:
                ch.pipeline.start()
            self.save()
            return ch.cid

    def remove_channel(self, cid):
        with self._lock:
            ch = self.channels.pop(cid, None)
            if not ch:
                return
            ch.pipeline.stop()
            self.engine.forget(cid)
            self.bus.publish("channels", cid, "removed")
            self.bus.drop(cid)
            self.save()

    def update_channel(self, cid, cfg):
        with self._lock:
            ch = self.channels[cid]
            restart = (cfg.get("url") != ch.cfg.get("url")
                       or cfg.get("decoder") != ch.cfg.get("decoder")
                       or cfg.get("quality") != ch.cfg.get("quality"))
            ch.cfg = dict(cfg)
            ch.state.name = cfg.get("name", "")
            ch.state.url = cfg.get("url", "")
            ch.state.th = self._thresholds(cfg)
            if restart:
                ch.boosted = False
                ch.pipeline.stop()
                ch.pipeline = self._build_pipeline(ch)
                if self._running:
                    ch.pipeline.start()
            self.bus.publish("channels", cid, "updated")
            self.save()

    def save(self):
        save_config([ch.cfg for ch in self.channels.values()],
                    self.defaults, self.config_path)

    # ── життєвий цикл ────────────────────────────────────────────────────────
    def start(self):
        self._running = True
        self.storage.start()
        for ch in list(self.channels.values()):
            ch.pipeline.start()
        threading.Thread(target=self._tick_loop, daemon=True).start()

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._stop.set()
        for ch in list(self.channels.values()):
            ch.pipeline.stop()
        self.storage.stop()

    # ── внутрішнє ────────────────────────────────────────────────────────────
    def _thresholds(self, cfg):
        return {**self.defaults,
                **{k: cfg[k] for k in DEFAULT_THRESHOLDS if k in cfg}}

    def _create(self, cfg):
        cid = self._next
        self._next += 1
        state = ChannelState(cid, cfg.get("name", f"Канал {cid}"),
                             cfg.get("url", ""), self._thresholds(cfg))
        ch = Channel(cid, cfg, state)
        ch.pipeline = self._build_pipeline(ch)
        self.channels[cid] = ch
        return ch

    def _build_pipeline(self, ch):
        cid, st, bus = ch.cid, ch.state, self.bus

        from analyzers.video import VideoAnalyzer
        va = VideoAnalyzer()
                
        def on_frame(d):
            st.on_video(*va.process(d))
            bus.publish("frame", cid, d)

        def on_status(s):
            if s.startswith("NO_SIGNAL"):
                va.reset()
            st.on_status(s)
            bus.publish("status", cid, s)

        def on_audio(db):
            st.on_audio(db)
            bus.publish("audio", cid, db)
            
        return ChannelPipeline(
            ch.cfg.get("url", ""), ch.cfg.get("decoder", self.decoder),
            on_frame=on_frame,
            on_status=on_status, on_audio=on_audio, on_stats=st.on_stats, quality=self._quality(ch))

    def _tick_loop(self):
        while not self._stop.wait(1.0):
            for ch in list(self.channels.values()):
                try:
                    snap = ch.state.snapshot()
                    self.bus.publish("metrics", ch.cid, snap)
                    self.engine.update(ch.cid, ch.state.name, snap, ch.state.th)
                    self.storage.add_metric(ch.state.name, snap)
                except Exception as e:
                    print(f"[tick {ch.cid}] {e}")
    
    def move_channel(self,cid, delta):
        with self._lock:
            ids = list(self.channels)
            i = ids.index(cid)
            j = i + delta
            if not 0 <= j < len(ids):
                return
            ids[i], ids[j] = ids[j], ids[i]
            self.channels = {k: self.channels[k] for k in ids}
            self.bus.publish("channels", cid, "moved")
            self.save()
    
    
    def set_defaults(self, new_defaults):
        with self._lock:
            self.defaults = {**DEFAULT_THRESHOLDS, **new_defaults}
            for ch in self.channels.values():
                ch.state.th = self._thresholds(ch.cfg)
            self.save()
    
    def replace_all(self, streams):
        with self._lock:
            for cid in list(self.channels):
                self.remove_channel(cid)
            for s in streams:
                self.add_channel(s)
    def _quality(self, ch):
        if ch.boosted:
            return "full"
        return ch.cfg.get("quality") or self.defaults.get("quality", "full")

    def current_quality(self, cid):
        return self._quality(self.channels[cid])

    def toggle_boost(self, cid):
        """Подвійний клік: тимчасово full, повторний повертає налаштований рівень."""
        with self._lock:
            ch = self.channels.get(cid)
            if not ch:
                return
            base = ch.cfg.get("quality") or self.defaults.get("quality", "full")
            if base == "full":
                return
            ch.boosted = not ch.boosted
            q = self._quality(ch)
            ch.pipeline.set_quality(q)
            self.bus.publish("quality", cid, q)