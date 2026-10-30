import numpy as np

W, H = 320, 180


class VideoAnalyzer:
    """Аналіз кадрів плитки (rgb24 320x180): яскравість, розкид, різниця з попереднім."""

    def __init__(self):
        self._prev = None

    def reset(self):
        self._prev = None

    def process(self, data):
        a = np.frombuffer(data, dtype=np.uint8).reshape(H, W, 3)
        g = a[::2, ::2, 1].astype(np.int16)         # зелений канал ≈ яскравість, крок 2
        mean = float(g.mean())
        std = float(g.std())
        diff = None
        if self._prev is not None and self._prev.shape == g.shape:
            diff = float(np.abs(g - self._prev).mean())
        self._prev = g
        return mean, std, diff