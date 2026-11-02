import sys, threading, time, urllib.request

url, n, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
res = {}

def worker(i):
    last, cc_err, pk, resync, total = {}, 0, 0, 0, 0
    buf, t0 = b"", time.time()
    try:
        r = urllib.request.urlopen(url, timeout=10)
        while time.time() - t0 < secs:
            d = r.read(65536)
            if not d:
                break
            buf += d
            total += len(d)
            pos = 0
            while len(buf) - pos >= 188:
                if buf[pos] != 0x47:
                    nxt = buf.find(b"\x47", pos + 1)
                    resync += 1
                    pos = nxt if nxt != -1 else len(buf)
                    continue
                pid = ((buf[pos + 1] & 0x1F) << 8) | buf[pos + 2]
                afc, cc = (buf[pos + 3] >> 4) & 3, buf[pos + 3] & 15
                if pid != 0x1FFF and afc & 1:
                    p = last.get(pid)
                    if p is not None and cc not in (p, (p + 1) & 15):
                        cc_err += 1
                    last[pid] = cc
                pk += 1
                pos += 188
            buf = buf[pos:]
    except Exception as e:
        res[i] = f"помилка: {e}"
        return
    res[i] = f"{total*8/secs/1000:.0f} kbps, пакетів {pk}, CC-помилок {cc_err}, ресинхр. {resync}"

ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
[t.start() for t in ts]
[t.join() for t in ts]
for i in sorted(res):
    print(i, res[i])