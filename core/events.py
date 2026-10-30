import threading

class EventBus:
    
    def __init__(self):
        self._subs = {}
        self._lock = threading.Lock()
        
    def subscribe(self, topic, cid, cb):
        with self._lock:
            k = (topic, cid)
            self._subs[k] = self._subs.get(k, ()) + (cb,)
            
    def drop(self, cid):
        
        with self._lock:
            for k in [k for k in self._subs if k[1] == cid]:
                del self._subs[k]
    
    def publish(self, topic, cid, payload):
        for key in ((topic, cid), (topic, None)):
            for cb in self._subs.get(key, ()):
                try:
                    cb(cid, payload)
                except Exception as e:
                    print(f"[bus] {topic}/{cid}: {e}")