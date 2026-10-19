"""Optional standard 5.1 routing before legacy first-two-channel extraction."""
import numpy as np


class ChannelMixer:
    def __init__(self):
        self.rear = 0.
        self.lfe = 0.
        self.gain = 1.
        self.soft_mix = None

    def process(self, data, channels, rate, rear=False, lfe=False, limiter='hard'):
        if limiter not in ('hard', 'soft'):
            raise ValueError('알 수 없는 합산 제한 방식')
        # Never infer 7.1/custom layouts. Stereo path is byte-for-byte unchanged.
        if channels != 6:
            self.rear = self.lfe = 0.
            self.gain = 1.
            self.soft_mix = None
            return data
        if not rear and not lfe and self.rear == 0 and self.lfe == 0 and self.gain == 1:
            self.soft_mix = float(limiter == 'soft')
            return data
        x = np.frombuffer(data, '<i2').reshape(-1, 6)
        n = len(x)
        if not n:
            return data
        # 30 ms linear coefficient slew, independent of capture block length.
        def ramp(current, target, maximum):
            length = max(1, round(rate * .03))
            start = round(current / maximum * length)
            end = round(target / maximum * length)
            positions = start + np.sign(end-start)*np.arange(1, n+1)
            return np.clip(positions, min(start,end), max(start,end)) / length * maximum
        r = ramp(self.rear, .5 if rear else 0., .5)
        f = ramp(self.lfe, .25 if lfe else 0., .25)
        self.rear, self.lfe = float(r[-1]), float(f[-1])
        # FL FR FC LFE surround-L surround-R. FC is never summed.
        # Front remains unity; only actual over-range sums trigger limiting.
        mixed = x[:, :2].astype(np.float64) + r[:, None]*x[:, 4:6] + f[:, None]*x[:, 3:4]
        hard = np.clip(mixed, -32768, 32767)
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
        soft = mixed * gains[:, None]
        target = float(limiter == 'soft')
        if self.soft_mix is None:
            self.soft_mix = target
        # Crossfade limiting policies over 20 ms without reopening devices.
        step = 1 / max(1, round(rate * .02))
        blend = self.soft_mix + np.clip(target-self.soft_mix, -step*np.arange(1,n+1), step*np.arange(1,n+1))
        self.soft_mix = float(blend[-1])
        mixed = hard*(1-blend[:,None]) + soft*blend[:,None]
        result = x.copy()
        result[:, :2] = np.clip(np.rint(mixed), -32768, 32767).astype('<i2')
        return result.tobytes()
