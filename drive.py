# KS3029 mecanum robot: SBUS radio drive.
# AETR: CH1 roll=strafe, CH2 pitch=fwd/back, CH3 throttle=speed limit,
# CH4 yaw=rotate, CH6 mode (manual / assisted / autonomous), CH7 arm
# (3-position switch: only the +1 end arms).
# Dry run without moving wheels: mpremote exec "import drive; drive.main(dry_run=True, secs=30)"
import time
import settings
from leds import Leds
from motors import Motors, WHEELS
from sbus import SBus, norm

LOOP_MS = 10
LINK_TIMEOUT_MS = 100
DEADBAND = 0.05
FULL = 0.9              # sticks/throttle reach only ~0.94-0.97: treat this as full
CENTERED = 0.1         # sticks must be within this to arm
CH_ROLL, CH_PITCH, CH_THR, CH_YAW, CH_MODE, CH_ARM = 0, 1, 2, 3, 5, 6

MANUAL, ASSISTED, AUTO = 0, 1, 2
MODE_NAMES = ("manual", "assisted", "auto")

# LED colors (dim)
OFF = (0, 0, 0)
RED = (40, 0, 0)
AMBER = (40, 15, 0)
BLUE = (0, 0, 40)
MODE_COLORS = ((0, 40, 0), (0, 30, 30), (30, 0, 30))  # green / cyan / magenta

# Chained WS2812 strips on GP3 (was the ultrasonic trigger), powered from the
# sensor shield's 5 V (rated 200 mA): 16 white at the front, then 14 red.
# Estimated draw: ~113 mA white + ~32 mA red = ~145 mA (incl. ~1 mA idle per LED).
STRIP_PIN = 3
STRIP_WHITE = (16, (30, 30, 30))   # front: brighter
STRIP_RED = (14, (16, 0, 0))       # rear: dim
STRIP_LEDS = STRIP_WHITE[0] + STRIP_RED[0]
STRIP_MAX_MA = 150      # hard cap: everything is dimmed further if the colors above exceed it


def shape(x, expo):
    if -DEADBAND < x < DEADBAND:
        return 0.0
    s = 1.0 if x > 0 else -1.0
    x = min(1.0, (abs(x) - DEADBAND) / (FULL - DEADBAND))
    return s * ((1.0 - expo) * x + expo * x * x * x)


SPIN_BAND = 0.05   # below this much movement, yaw blends into spinning on the spot


def mix(p, r, y, arc=1.0, trim=None):
    """Car-like steering: the yaw stick sets how tight the turn is relative
    to the current speed, so the robot never stops to spin while it is
    moving. Full yaw (arc 1.0) stops the inner wheels: a pivot turn.
    Only with the movement sticks centered does yaw spin on the spot."""
    # The per-wheel trim keeps forward/back straight. It scales only the pitch
    # part: on a sideways move the diagonal wheels (FL+RR, FR+RL) must turn
    # equally, or they fight each other and the robot shakes.
    t = trim or {}
    fl, fr, rl, rr = (p * t.get(k, 1.0) for k in ("FL", "FR", "RL", "RR"))
    move = [fl + r, fr - r, rl - r, rr + r]
    m = max(abs(v) for v in move)
    if m > 1.0:
        move = [v / m for v in move]
        m = 1.0
    # Turn rate proportional to speed while moving; full spin when standing.
    s = max(0.0, 1.0 - m / SPIN_BAND)
    yaw = y * (arc * m * (1.0 - s) + s)
    w = [move[0] + yaw, move[1] - yaw, move[2] + yaw, move[3] - yaw]
    if s == 0.0 and arc <= 1.0:
        # While moving, an inner wheel may stop but never reverse: with the
        # start duty a tiny negative command would kick it backwards.
        w = [0.0 if v * mv < 0.0 else v for v, mv in zip(w, move)]
    # Out of headroom: scale everything together so the turn keeps its shape.
    top = max(abs(v) for v in w)
    if top > 1.0:
        w = [v / top for v in w]
    return {"FL": w[0], "FR": w[1], "RL": w[2], "RR": w[3]}


class Recorder:
    """Keeps the last LOG_N samples while armed (RAM only) and dumps them to
    log.bin on disarm (raw int16 x1000, instant to write), so a drive can be
    analyzed afterwards without a cable. Convert on the PC: tools/log2csv.py"""
    FIELDS = ("raw_yaw", "p", "r", "y", "lim", "FL", "FR", "RL", "RR")
    LOG_N = 600          # 30 s at 20 Hz
    LOG_MS = 50

    def __init__(self):
        import array
        self.buf = array.array("h", bytes(2 * len(self.FIELDS) * self.LOG_N))
        self.i = self.count = 0
        self.moved = False
        self.next = time.ticks_ms()

    def add(self, t0, values):
        if time.ticks_diff(t0, self.next) < 0:
            return
        self.next = time.ticks_add(t0, self.LOG_MS)
        base = self.i * len(self.FIELDS)
        for j, v in enumerate(values):
            self.buf[base + j] = int(max(-32, min(32, v)) * 1000)
        if any(values[5:]):
            self.moved = True
        self.i = (self.i + 1) % self.LOG_N
        self.count = min(self.count + 1, self.LOG_N)

    def save(self, name="log.bin"):
        # Arm/disarm without driving keeps the previous log.
        if self.moved:
            nf = len(self.FIELDS)
            mv = memoryview(self.buf)
            with open(name, "wb") as f:
                if self.count == self.LOG_N:   # ring is full: oldest first
                    f.write(mv[self.i * nf:])
                f.write(mv[:self.i * nf])
            print("log saved:", self.count, "samples")
        self.i = self.count = 0
        self.moved = False


def main(dry_run=False, secs=None, until_disarm=False):
    """dry_run: compute everything but keep the motors stopped.
    until_disarm: return after the first arm -> disarm cycle (for bench tests)."""
    cfg = settings.load()
    expo = cfg["expo"]
    yaw_expo = cfg["yaw_expo"]
    arc = cfg["arc"]
    zero_ramp = cfg["zero_ramp"]
    speed_min = cfg["speed_min"]
    trim = cfg["trim"]
    slew = cfg["slew_per_s"] * LOOP_MS / 1000
    rev = [c - 1 for c in cfg["ch_reverse"]]
    debug = cfg["debug"]

    motors = Motors(cfg["invert"], cfg["min_duty"], cfg["max_duty"], cfg["start_boost"])
    motors.seven_color(False, False)  # front strobe LEDs: always off
    leds = Leds()
    leds.show(RED)
    strip = Leds(STRIP_PIN, STRIP_LEDS, sm=1, max_ma=STRIP_MAX_MA)
    strip.show_segments((STRIP_WHITE, STRIP_RED))
    rx = SBus()

    armed = False
    arm_ready = False     # arm switch seen OFF with a good link since boot/failsafe
    mode = MANUAL
    out = {w: 0.0 for w in WHEELS}
    rec = Recorder()
    start = next_print = next_strip = time.ticks_ms()
    print("drive: disarmed, cycle arm switch off->on to arm",
          "(DRY RUN, motors stay off)" if dry_run else "")

    try:
        while secs is None or time.ticks_diff(time.ticks_ms(), start) < secs * 1000:
            t0 = time.ticks_ms()
            rx.poll()
            link = rx.link_ok(t0, LINK_TIMEOUT_MS)

            p = r = y = 0.0
            lim = speed_min
            arm_sw = False
            if link:
                ch = [-norm(v) if i in rev else norm(v)
                      for i, v in enumerate(rx.ch[:7])]
                r = shape(ch[CH_ROLL], expo)
                p = shape(ch[CH_PITCH], expo)
                y = shape(ch[CH_YAW], yaw_expo)
                thr = min(1.0, (ch[CH_THR] + 1.0) / (FULL + 1.0))
                lim = speed_min + (1.0 - speed_min) * thr
                arm_sw = ch[CH_ARM] > 0.5
                m = ch[CH_MODE]
                mode = MANUAL if m < -0.33 else AUTO if m > 0.33 else ASSISTED

            # Arming: needs a fresh off->on of the arm switch, sticks centered.
            was_armed = armed
            if not link:
                armed = False
                arm_ready = False
            elif not arm_sw:
                armed = False
                arm_ready = True
            elif arm_ready and not armed:
                if abs(p) < CENTERED and abs(r) < CENTERED and abs(y) < CENTERED:
                    armed = True
                    arm_ready = False
            if armed != was_armed:
                print("ARMED" if armed else "DISARMED", "" if link else "(no link / failsafe)")
                if was_armed:
                    motors.stop()
                    rec.save()
                if until_disarm and was_armed:
                    break

            if armed and mode != AUTO:
                # ASSISTED drives like MANUAL until ultrasonic/line assists exist.
                # Blend on the raw sticks, then scale, so the throttle limit
                # does not change how turns feel.
                target = mix(p, r, y, arc, trim)
                for w in WHEELS:
                    target[w] *= lim
                # Start-duty fade zone, as a share of the current top speed.
                motors.ramp = zero_ramp * lim
                for w in WHEELS:
                    d = target[w] - out[w]
                    # Slowing down may happen twice as fast as speeding up.
                    step = slew * 2 if abs(target[w]) < abs(out[w]) else slew
                    if d > step:
                        d = step
                    elif d < -step:
                        d = -step
                    out[w] += d
                    motors.set(w, 0.0 if dry_run else out[w])
                rec.add(t0, (ch[CH_YAW], p, r, y, lim,
                             out["FL"], out["FR"], out["RL"], out["RR"]))
            else:
                for w in WHEELS:
                    out[w] = 0.0
                    motors.set(w, 0.0)

            if not link:
                leds.show(RED if (t0 // 250) % 2 else OFF)
            elif armed:
                leds.show(MODE_COLORS[mode])
            elif arm_ready:
                leds.show(BLUE)
            else:
                leds.show(AMBER)  # arm switch still on: cycle it

            # The strip may get its 5 V after boot (battery switched on later).
            if time.ticks_diff(t0, next_strip) >= 0:
                next_strip = time.ticks_add(t0, 1000)
                strip.refresh()

            if debug and time.ticks_diff(t0, next_print) >= 0:
                next_print = time.ticks_add(t0, 500)
                print("link" if link else "NOLINK",
                      "ARM" if armed else "dis", MODE_NAMES[mode],
                      "p%+.2f r%+.2f y%+.2f lim%.2f" % (p, r, y, lim),
                      " ".join("%s%+.2f" % (w, out[w]) for w in WHEELS),
                      "raw2:%d raw7:%d" % (rx.ch[CH_PITCH], rx.ch[CH_ARM]),
                      "fr", rx.frames, "bad", rx.bad, "i2cerr", motors.errors)

            dt = time.ticks_diff(time.ticks_ms(), t0)
            if dt < LOOP_MS:
                time.sleep_ms(LOOP_MS - dt)
    finally:
        motors.stop()
        motors.seven_color(False, False)
        leds.show(OFF)
        strip.show(OFF)
        print("drive stopped, motors off")
