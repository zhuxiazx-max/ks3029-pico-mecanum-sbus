# Step 1 bench test. WHEELS OFF THE GROUND.
#   mpremote exec "import bench; bench.spin('FL')"   spin raw register A
#   mpremote exec "import bench; bench.set_dir('FL', False)"  True if it ran backward
#   mpremote exec "import bench; bench.verify()"     all wheels with saved flags
# Or interactively in the REPL: import bench; bench.run()
import time
import settings
from motors import Motors, WHEELS, NAMES

DUTY = 120
SECS = 2.0


def spin(wheel, duty=DUTY, secs=SECS, use_flags=False):
    cfg = settings.load()
    m = Motors(cfg["invert"] if use_flags else {}, 0)
    print("Spinning", wheel, "(" + NAMES[wheel] + ")", "duty", duty)
    try:
        m.raw(wheel, duty)
        time.sleep(secs)
    finally:
        m.stop()
    print("stopped")


def spin_pair(a, duty=DUTY, secs=SECS):
    """Drive register a (b = a + 1 stays 0) to find which wheel a pair moves."""
    m = Motors({}, 0)
    print("Spinning registers", a, "/", a + 1, "duty", duty)
    try:
        m._write(a + 1, 0)
        m._write(a, duty)
        time.sleep(secs)
    finally:
        m.stop()
    print("stopped")


def set_dir(wheel, backward):
    """Store the result for a wheel spun with spin(): backward=True inverts it."""
    cfg = settings.load()
    cfg["invert"][wheel] = bool(backward)
    settings.save(cfg)
    print(wheel, "invert =", cfg["invert"][wheel])


def verify(secs=1.5):
    for w in WHEELS:
        spin(w, DUTY, secs, use_flags=True)
        time.sleep(0.5)


SWEEP = (20, 30, 40, 55, 70, 90, 120, 160, 210, 255)


def sweep(duties=SWEEP, on_s=2.0, off_s=1.0):
    """All wheels forward in numbered bursts, to find where they start and
    where they stop getting faster. Count the bursts while watching."""
    m = Motors(settings.load()["invert"], 0)
    try:
        for i, d in enumerate(duties):
            print("burst", i + 1, "duty", d)
            for w in WHEELS:
                m.raw(w, d)
            time.sleep(on_s)
            m.stop()
            time.sleep(off_s)
    finally:
        m.stop()
    print("stopped")


START = (20, 25, 30, 35, 40, 45, 50, 55, 60, 70)


def start_sweep(duties=START, on_s=3.0, off_s=1.5, direction=1):
    """WHEELS UP. All wheels at rising low duties (direction -1 = backward),
    to find the duty where each one starts. During burst N the first N strip
    LEDs light up, so the burst can be counted without watching the console."""
    from leds import Leds
    strip = Leds(3, 30, sm=1, max_ma=150)
    m = Motors(settings.load()["invert"], 0)
    try:
        for i, d in enumerate(duties):
            print("burst", i + 1, "duty", d)
            strip.show_segments(((i + 1, (30, 30, 30)),))
            for w in WHEELS:
                m.raw(w, d * direction)
            time.sleep(on_s)
            m.stop()
            strip.show((0, 0, 0))
            time.sleep(off_s)
    finally:
        m.stop()
        strip.show((0, 0, 0))
    print("stopped")


def run():
    for w in WHEELS:
        spin(w)
        ans = input("Did " + NAMES[w] + " turn forward? [y/n] ").strip().lower()
        set_dir(w, ans.startswith("n"))
    print("Saved:", settings.load()["invert"])
