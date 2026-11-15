# Persistent robot settings, stored as config.json on the Pico.
import json

FILE = "config.json"

DEFAULTS = {
    # True = this wheel's "forward" is the second register of its pair
    "invert": {"FL": False, "FR": False, "RL": False, "RR": False},
    # per-wheel speed scale, to slow the faster side so the robot drives straight
    "trim": {"FL": 1.0, "FR": 1.0, "RL": 1.0, "RR": 1.0},
    # extra start duty per wheel, for a motor that starts later than the others
    "start_boost": {"FL": 5, "FR": 0, "RL": 0, "RR": 0},
    "min_duty": 50,       # duty where wheels keep turning on the floor (wheels up: 40)
    "max_duty": 255,      # duty at full stick and full throttle
    "arc": 1.0,           # full yaw while moving: 1.0 = inner wheels stop (pivot), >1 tighter
    "expo": 0.6,          # 0 = linear sticks; higher = finer control near center
    "yaw_expo": 0.0,      # expo for yaw only: 0 = turn rate grows evenly with the stick
    "zero_ramp": 0.0,     # share of stick travel over which a wheel fades in from stop
    "speed_min": 0.15,    # speed limit with the throttle at the bottom (1.0 = full)
    "slew_per_s": 4.0,    # max change of wheel command per second (1.0 = full scale)
    "ch_reverse": [],     # 1-based channel numbers to flip, e.g. [2]
    "debug": True,        # print status twice a second
}


def load():
    cfg = dict(DEFAULTS)
    for k in ("invert", "trim", "start_boost"):
        cfg[k] = dict(DEFAULTS[k])
    try:
        with open(FILE) as f:
            saved = json.load(f)
        cfg.update(saved)
        for k in ("invert", "trim", "start_boost"):
            d = dict(DEFAULTS[k])
            d.update(saved.get(k, {}))
            cfg[k] = d
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    with open(FILE, "w") as f:
        json.dump(cfg, f)


def set(key, value):
    """Change one setting from the REPL, e.g. settings.set("min_duty", 70)."""
    cfg = load()
    cfg[key] = value
    save(cfg)
    print(key, "=", value)
