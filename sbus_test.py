# Step 2: print SBUS channels live.
#   mpremote run sbus_test.py                      (Ctrl-C to stop)
#   mpremote exec "import sbus_test; sbus_test.watch(20)"   for 20 seconds
import time
from sbus import SBus, norm, FLAG_FAILSAFE, FLAG_LOST
from motors import Motors


def watch(secs=None, every_ms=200):
    Motors().stop()  # make sure nothing is left spinning
    rx = SBus()
    start = last = time.ticks_ms()
    while secs is None or time.ticks_diff(time.ticks_ms(), start) < secs * 1000:
        rx.poll()
        now = time.ticks_ms()
        if time.ticks_diff(now, last) >= every_ms:
            last = now
            c = rx.ch
            print("ok" if rx.link_ok(now) else "NO LINK",
                  "fs" if rx.flags & FLAG_FAILSAFE else "--",
                  "lost" if rx.flags & FLAG_LOST else "----",
                  "frames", rx.frames, "bad", rx.bad, "|",
                  " ".join("%d:%4d(%+.2f)" % (i + 1, c[i], norm(c[i])) for i in range(8)))
        time.sleep_ms(2)


def changes(secs=30, threshold=0.2):
    """Print only channels that move, to find which switch drives which channel."""
    Motors().stop()
    rx = SBus()
    start = time.ticks_ms()
    ref = None
    had_link = None
    while time.ticks_diff(time.ticks_ms(), start) < secs * 1000:
        if rx.poll() and ref is None:
            ref = [norm(v) for v in rx.ch]
        now = time.ticks_ms()
        link = rx.link_ok(now)
        if link != had_link:
            had_link = link
            print("%5.1fs %s" % (time.ticks_diff(now, start) / 1000,
                                 "link ok" if link else "NO LINK / failsafe"))
        if ref is not None and link:
            for i in range(15):  # XM+ puts RSSI on CH16
                v = norm(rx.ch[i])
                if abs(v - ref[i]) >= threshold:
                    print("%5.1fs CH%d %+.2f -> %+.2f" % (
                        time.ticks_diff(now, start) / 1000, i + 1, ref[i], v))
                    ref[i] = v
        time.sleep_ms(5)
    print("done")


if __name__ == "__main__":
    watch()
