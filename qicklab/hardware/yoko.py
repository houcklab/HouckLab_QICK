import time

import numpy as np


def ramp_to(yoko, target, step=0.001, delay=0.01):
    if target > 10:  # charge-line limit, positive side only: docs/hardware.md#charge-bias-yoko
        raise ValueError("Voltage too high")
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")  # land exactly on target
