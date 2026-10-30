# bench.py   запуск: python bench.py <url|файл> <N> <cpu|cuda>
import subprocess, sys, threading, time, psutil

url, n, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]
W, H = 320, 180
if mode == "cuda":
    pre = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    vf = f"scale_cuda={W}:{H},hwdownload,format=nv12,fps=12"
else:
    pre = []
    vf = f"scale={W}:{H},fps=12"
loop = [] if "://" in url else ["-re", "-stream_loop", "-1"]
frames = [0] * n

def reader(i, p):
    size = W * H * 3
    while p.stdout.read(size):
        frames[i] += 1

procs = []
for i in range(n):
    cmd = ["ffmpeg", "-loglevel", "error", *pre, *loop, "-i", url, "-an",
           "-vf", vf, "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    procs.append(p)
    threading.Thread(target=reader, args=(i, p), daemon=True).start()

time.sleep(8)  # прогрів
alive = [p for p in procs if p.poll() is None]
print(f"живих процесів: {len(alive)}/{n}")
ps = [psutil.Process(p.pid) for p in alive]
def cpu(): return sum(x.cpu_times().user + x.cpu_times().system for x in ps)
t0, c0, f0 = time.time(), cpu(), sum(frames)
time.sleep(20)
dt = time.time() - t0
cores = (cpu() - c0) / dt
print(f"{mode} x{n}: {cores:.2f} ядра ffmpeg = "
      f"{cores / psutil.cpu_count() * 100:.2f}% машини, "
      f"{(sum(frames)-f0)/dt/len(alive):.1f} fps/потік")
for p in procs: p.kill()