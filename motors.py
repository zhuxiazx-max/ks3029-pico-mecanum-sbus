# Driver for the KS3029 STC8 motor co-processor (I2C 0x30).
# Replaces mecanumCar_v2.py, whose movement functions are wrong.
from machine import I2C, Pin

ADDR = 0x30
# (forward register, reverse register) per wheel, measured on the bench:
# the front pair is swapped vs. the Keyestudio docs, and the even register
# of each pair drives forward. Per-wheel invert flags can still flip one.
REGS = {"FR": (2, 1), "FL": (4, 3), "RR": (6, 5), "RL": (8, 7)}
WHEELS = ("FL", "FR", "RL", "RR")
NAMES = {"FL": "front left", "FR": "front right",
         "RL": "rear left", "RR": "rear right"}
REG_LED_RIGHT = 0x09
REG_LED_LEFT = 0x0A


class Motors:
    def __init__(self, invert=None, min_duty=40, max_duty=100, start_boost=None):
        """start_boost: extra min_duty per wheel, for a motor that needs more to start."""
        self.i2c = I2C(0, sda=Pin(20), scl=Pin(21), freq=400_000)
        self.invert = invert or {}
        self.min_duty = min_duty
        self.start_boost = start_boost or {}
        self.ramp = 0.0   # commands below this fade from 0 up to the start duty
        self.max_duty = max_duty
        self.errors = 0
        self._last = {}
        self.stop()

    def _write(self, reg, value):
        try:
            self.i2c.writeto_mem(ADDR, reg, bytes((value,)))
            return True
        except OSError:
            self.errors += 1
            return False

    def raw(self, wheel, duty):
        """duty -255..255; positive drives register A, after inversion."""
        duty = max(-255, min(255, int(duty)))
        if self.invert.get(wheel):
            duty = -duty
        last = self._last.get(wheel)
        if last == duty:
            return
        same_dir = last is not None and last != 0 and duty != 0 and (last > 0) == (duty > 0)
        # Ignore 1-step changes (stick noise): fewer I2C writes, steadier PWM.
        if same_dir and abs(duty - last) < 2:
            return
        a, b = REGS[wheel]
        if same_dir:
            # Opposite register is already 0: only update the speed.
            ok = self._write(a if duty > 0 else b, abs(duty))
        # Zero the opposite register first so both are never non-zero.
        elif duty >= 0:
            ok = self._write(b, 0) and self._write(a, duty)
        else:
            ok = self._write(a, 0) and self._write(b, -duty)
        if ok:
            self._last[wheel] = duty
        else:
            self._last.pop(wheel, None)  # retry on next call

    def set(self, wheel, w):
        """w -1.0..1.0; non-zero maps to min_duty..max_duty."""
        if -0.01 < w < 0.01:
            self.raw(wheel, 0)
            return
        lo = self.min_duty + self.start_boost.get(wheel, 0)
        a = min(abs(w), 1.0)
        duty = lo + a * (self.max_duty - lo)
        # Near zero, fade the start duty in instead of jumping straight to it,
        # so a wheel slowing down and reversing (the inner side in a turn)
        # passes smoothly through stop instead of flipping +lo -> -lo at once.
        if a < self.ramp:
            duty *= a / self.ramp
        self.raw(wheel, duty if w > 0 else -duty)

    def stop(self):
        """Zero every motor register unconditionally."""
        for reg in range(1, 9):
            self._write(reg, 0)
        self._last.clear()

    def seven_color(self, right, left):
        self._write(REG_LED_RIGHT, 1 if right else 0)
        self._write(REG_LED_LEFT, 1 if left else 0)
