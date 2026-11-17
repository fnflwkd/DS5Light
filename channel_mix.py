"""Optional standard 5.1 routing before legacy first-two-channel extraction."""
import numpy as np


class ChannelMixer:
    def __init__(self):
        self.rear = 0.
        self.lfe = 0.
        self.center = 0.
        self.gain = 1.
        self.soft_mix = None
        self._position_count = 0

    def process(self, data, channels, rate, rear=False, lfe=False, limiter='hard', center=False):
        if limiter not in ('hard', 'soft'):
            raise ValueError('알 수 없는 합산 제한 방식')
        # Never infer 7.1/custom layouts. Stereo path is byte-for-byte unchanged.
        if channels not in (6, 8):
            self.rear = self.lfe = self.center = 0.
            self.gain = 1.
            self.soft_mix = None
            return data
        if not rear and not lfe and not center and self.rear == 0 and self.lfe == 0 and self.center == 0 and self.gain == 1:
            self.soft_mix = float(limiter == 'soft')
            return data
        x = np.frombuffer(data, '<i2').reshape(-1, channels)
        n = len(x)
        if not n:
            return data
        if self._position_count != n:
            self._positions = np.arange(1,n+1)
            self._position_count = n
        # 30 ms linear coefficient slew, independent of capture block length.
        def ramp(current, target, maximum):
            length = max(1, round(rate * .03))
            start = round(current / maximum * length)
            end = round(target / maximum * length)
            positions = start + np.sign(end-start)*self._positions
            return np.clip(positions, min(start,end), max(start,end)) / length * maximum
        r = ramp(self.rear, .5 if rear else 0., .5)
        f = ramp(self.lfe, .25 if lfe else 0., .25)
        c = ramp(self.center, 2**-.5 if center else 0., 2**-.5)
        self.center = float(c[-1])
        self.rear, self.lfe = float(r[-1]), float(f[-1])
        # FL FR FC LFE surround-L surround-R. FC is optional, linked to both sides.
        # Front remains unity; only actual over-range sums trigger limiting.
        surround = x[:, 4:6] if channels == 6 else (x[:, 4:6].astype(np.float64) + x[:, 6:8]) * .5
        mixed = x[:, :2].astype(np.float64) + r[:, None]*surround + f[:, None]*x[:, 3:4] + c[:, None]*x[:, 2:3]
        # Linked stereo peak gain: immediate attack, linear recovery to unity
        # (at most 50 ms). No lookahead, no added audio buffering.
        overload = np.maximum(np.max(mixed, axis=1)/32767, -np.min(mixed, axis=1)/32768)
        required = 1 / np.maximum(1., overload)
        gains = np.empty(n)
        release_step = 1 / max(1, round(rate * .05))
        gain = self.gain
        for i in range(n):
            gain = min(float(required[i]), gain + release_step)
            gains[i] = gain
        self.gain = gain
        target = float(limiter == 'soft')
        if self.soft_mix is None:
            self.soft_mix = target
        # Crossfade limiting policies over 20 ms without reopening devices.
        step = 1 / max(1, round(rate * .02))
        start = self.soft_mix
        blend = self.soft_mix + np.clip(target-self.soft_mix, -step*self._positions, step*self._positions)
        self.soft_mix = float(blend[-1])
        if start == target == 0:
            mixed = np.clip(mixed, -32768, 32767)
        elif start == target == 1:
            mixed = mixed * gains[:, None]
        else:
            hard = np.clip(mixed, -32768, 32767)
            soft = mixed * gains[:, None]
            mixed = hard*(1-blend[:,None]) + soft*blend[:,None]
        result = x.copy()
        result[:, :2] = np.clip(np.rint(mixed), -32768, 32767).astype('<i2')
        return result.tobytes()
