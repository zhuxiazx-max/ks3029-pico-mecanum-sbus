# WS2812 LEDs via PIO (MicroPython 1.17 has no neopixel module):
# 4x status LEDs on GP7 / state machine 0, 30x strip on GP3 / state machine 1.
import array
import rp2
from machine import Pin


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=24)
def _ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0)    [T3 - 1]
    jmp(not_x, "do_zero")   .side(1)    [T1 - 1]
    jmp("bitloop")          .side(1)    [T2 - 1]
    label("do_zero")
    nop()                   .side(0)    [T2 - 1]
    wrap()


# WS2812 current, worst case: ~20 mA per color channel at 255, ~1 mA idle per LED.
MA_PER_CHANNEL = 20
MA_IDLE = 1


def current_ma(n, color):
    """Estimated draw of n LEDs all showing color (r, g, b)."""
    return n * (MA_IDLE + sum(color) * MA_PER_CHANNEL / 255)


class Leds:
    def __init__(self, pin=7, n=4, sm=0, max_ma=None):
        """max_ma: dim every color so the estimated draw stays below this."""
        self.sm = rp2.StateMachine(sm, _ws2812, freq=8_000_000, sideset_base=Pin(pin))
        self.sm.active(1)
        self.buf = array.array("I", [0] * n)
        self.max_ma = max_ma
        self._color = None

    def show(self, color):
        """Set all LEDs to (r, g, b); only writes when the color changes."""
        self.show_segments(((len(self.buf), color),))

    def show_segments(self, segments):
        """segments: ((count, (r, g, b)), ...) from the first LED on; LEDs past
        the last segment stay off. If max_ma is set, all colors are dimmed by
        the same factor so the estimated total stays below it."""
        segments = tuple(segments)
        if segments == self._color:
            return
        self._color = segments
        n = len(self.buf)
        total = sum(current_ma(c, col) for c, col in segments)
        k = 1.0
        if self.max_ma and total > self.max_ma:
            k = (self.max_ma - n * MA_IDLE) / (total - n * MA_IDLE)
        i = 0
        for count, color in segments:
            r, g, b = (int(c * k) for c in color)
            grb = ((g << 16) | (r << 8) | b) << 8
            for _ in range(count):
                if i < n:
                    self.buf[i] = grb
                    i += 1
        while i < n:
            self.buf[i] = 0
            i += 1
        self.sm.put(self.buf)

    def refresh(self):
        """Resend the current colors, e.g. for a strip that was powered up later."""
        self.sm.put(self.buf)
