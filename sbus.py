# SBUS receiver on UART1 RX = GP5 (FrSky XM+).
from machine import UART, Pin
import time

FLAG_LOST = 0x04
FLAG_FAILSAFE = 0x08


def norm(v):
    """SBUS 172..1811 -> -1.0..1.0 (center 992)."""
    x = (v - 992) / 819
    return -1.0 if x < -1.0 else 1.0 if x > 1.0 else x


def decode(frame, ch):
    """Unpack 16 x 11-bit channels from frame[1:23] into list ch."""
    acc = 0
    bits = 0
    idx = 0
    for i in range(1, 23):
        acc |= frame[i] << bits
        bits += 8
        while bits >= 11:
            ch[idx] = acc & 0x7FF
            acc >>= 11
            bits -= 11
            idx += 1


class SBus:
    def __init__(self, rx=5, tx=8):
        # UART1's default TX is GP4 (ultrasonic echo), so park TX on unused GP8.
        self.uart = UART(1, baudrate=100000, bits=8, parity=0, stop=2,
                         tx=Pin(tx), rx=Pin(rx), invert=UART.INV_RX, rxbuf=256)
        self.ch = [992] * 16
        self.flags = 0
        self.frames = 0
        self.bad = 0
        self.lost = 0
        self.last_ms = None
        self._f = bytearray(25)
        self._n = 0
        self._rx = bytearray(64)

    def poll(self):
        """Consume pending bytes. Returns True if a new good frame arrived."""
        got = False
        while True:
            n = self.uart.any()
            if not n:
                return got
            n = self.uart.readinto(self._rx, min(n, len(self._rx)))
            if not n:
                return got
            for i in range(n):
                if self._byte(self._rx[i]):
                    got = True

    def _byte(self, b):
        if self._n == 0 and b != 0x0F:
            return False
        self._f[self._n] = b
        self._n += 1
        if self._n < 25:
            return False
        if b == 0x00:
            decode(self._f, self.ch)
            self.flags = self._f[23]
            if self.flags & FLAG_LOST:
                self.lost += 1
            self.frames += 1
            self.last_ms = time.ticks_ms()
            self._n = 0
            return True
        # Bad end byte: resync at the next 0x0F inside the buffer.
        self.bad += 1
        f = self._f
        for j in range(1, 25):
            if f[j] == 0x0F:
                f[0:25 - j] = f[j:25]
                self._n = 25 - j
                return False
        self._n = 0
        return False

    def link_ok(self, now, timeout_ms=100):
        return (self.last_ms is not None
                and time.ticks_diff(now, self.last_ms) < timeout_ms
                and not self.flags & FLAG_FAILSAFE)
