"""One color per FF channel / qubit lane, shared by the GUI and the plots from exported scripts."""

QUBIT_COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2", "#EECA3B", "#9D755D"]


def qubit_color_hex(q: int) -> str:
    return QUBIT_COLORS[(int(q) - 1) % len(QUBIT_COLORS)]
