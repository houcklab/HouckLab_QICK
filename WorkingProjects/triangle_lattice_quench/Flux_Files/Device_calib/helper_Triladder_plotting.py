import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np


def _triladder_positions(n_qubits):
    '''Zigzag coords: Qq at column q-1 (odd->top, even->bottom); Ck midway between Qk and Q(k+2).'''
    dx, x0, top_y = 0.25, 0.225, 0.4
    bot_y = top_y - dx * np.sqrt(2)
    row_y = lambda idx: top_y if idx % 2 == 1 else bot_y
    qubit_pos = {f"Q{q}": np.array((x0 + (q - 1) * dx, row_y(q))) for q in range(1, n_qubits + 1)}
    coupler_pos = {f"C{k}": np.array((x0 + k * dx, row_y(k))) for k in range(1, n_qubits - 1)}
    return qubit_pos, coupler_pos


def plot_bare_triladder(freqs_dict, couplings_dict):
    '''Bare qubits (circles) + couplers (triangles) with all couplings from couplings_dict {(a,b): g}.'''

    n_qubits = sum(1 for name in freqs_dict if name[0] == "Q")
    qubit_pos, coupler_pos = _triladder_positions(n_qubits)
    pos = {**qubit_pos, **coupler_pos}

    fig, ax = plt.subplots(figsize=(1.5 * n_qubits, 5))  # note we must use plt.subplots, not plt.subplot

    for name, coord in pos.items():
        above = int(name[1:]) % 2 == 1  # top-row nodes label above, bottom-row below
        if name[0] == "Q":
            patch = plt.Circle(coord, 0.04, edgecolor='maroon', facecolor='indianred', zorder=10, lw=2)
            fc, ec = "pink", "maroon"
        else:
            patch = patches.RegularPolygon(coord, 3, radius=0.04, edgecolor='darkblue', facecolor='cornflowerblue',
                                           zorder=10, lw=2)
            fc, ec = "lightblue", "steelblue"
        ax.add_patch(patch)
        ax.text(coord[0], coord[1], name, ha='center', va='center', fontsize=10, color='white', zorder=11)
        # Qubit/coupler frequency box
        ax.annotate(np.round(freqs_dict[name], 1), coord + (-0.04, 0.09 if above else -0.09),
                    bbox=dict(boxstyle="round,pad=0.4", fc=fc, ec=ec, lw=2), zorder=11)

    ARC_HEIGHT = 0.2
    for (a, b), g in couplings_dict.items():
        ca, cb = pos[a], pos[b]
        location = (ca + cb) / 2
        both_qubits = a[0] == "Q" and b[0] == "Q"
        if both_qubits and abs(int(a[1:]) - int(b[1:])) == 2:
            # Direct next-nearest qubit coupling (parallels a coupler): draw as an arc
            up = int(a[1:]) % 2 == 1  # both endpoints share row parity
            theta1 = 0 if up else 180
            path = patches.Arc(location, np.abs(cb - ca)[0], ARC_HEIGHT * 2, theta1=theta1, theta2=theta1 + 180)
            ax.add_patch(path)
            ax.annotate(np.round(g, 1), location + (-0.03, ARC_HEIGHT * (1 if up else -1)),
                        bbox=dict(boxstyle="round,pad=0.4", fc="xkcd:pale turquoise", ec="xkcd:sea", lw=2))
        else:
            # Rung coupling or qubit-coupler coupling: straight line
            path = patches.ConnectionPatch(xyA=ca, coordsA=ax.transData, xyB=cb, lw=1)
            ax.add_patch(path)
            ax.annotate(np.round(g, 1), location + (-0.03, 0),
                        bbox=dict(boxstyle="round,pad=0.4", fc="xkcd:pale turquoise", ec="xkcd:sea", lw=2))

    ax.axis("equal")
    ax.axis("off")
    plt.show(block=False)

    return ax


def plot_dressed_triladder(freqs_dict, gammas_dict, ax=None):
    """Dressed qubits + effective qubit-qubit couplings gammas_dict {(Qi,Qj): g}; plaquettes shaded 0/pi by sign.

    Args:
        freqs_dict:  {qubit_name: dressed frequency}
        gammas_dict: {(qubit_i, qubit_j): effective coupling}, sorted-name keys
        ax:          optional matplotlib Axes to draw into. If None, a new
                     figure+axes are created and returned.
    """
    n_qubits = sum(1 for name in freqs_dict if name[0] == "Q")
    qubit_pos, _ = _triladder_positions(n_qubits)

    created_fig = ax is None
    if created_fig:
        fig, ax = plt.subplots(figsize=(1.0 * n_qubits, 5))  # standalone usage
    else:
        fig = ax.figure

    for q in range(1, n_qubits + 1):
        name, coord = f"Q{q}", qubit_pos[f"Q{q}"]
        above = q % 2 == 1
        # Qubit: Red circle
        ax.add_patch(plt.Circle(coord, 0.04, edgecolor='maroon', facecolor='indianred', zorder=10, lw=2))
        ax.text(coord[0], coord[1], name, ha='center', va='center', fontsize=10, color='white', zorder=11)
        # Qubit frequency box
        ax.annotate(np.round(freqs_dict[name], 1), coord + (-0.04, 0.09 if above else -0.09),
                    bbox=dict(boxstyle="round,pad=0.4", fc="pink", ec="maroon", lw=2), zorder=11)

    for (a, b), g in gammas_dict.items():
        ca, cb = qubit_pos[a], qubit_pos[b]
        path = patches.ConnectionPatch(xyA=ca, coordsA=ax.transData, xyB=cb, lw=1)
        ax.add_patch(path)
        ax.annotate(np.round(g, 1), (ca + cb) / 2 + (-0.01, 0),
                    bbox=dict(boxstyle="round,pad=0.4",
                              fc="xkcd:pale turquoise" if g > 0 else "xkcd:pale lavender",
                              ec="xkcd:sea" if g > 0 else "xkcd:periwinkle", lw=2))

    # 0 or Pi plaquettes: sign of the Qk-Q(k+2) effective coupling (the triangle's closing edge)
    for q in range(1, n_qubits - 1):
        tri = [qubit_pos[f"Q{q}"], qubit_pos[f"Q{q + 1}"], qubit_pos[f"Q{q + 2}"]]
        g_closing = gammas_dict[tuple(sorted((f"Q{q}", f"Q{q + 2}")))]
        flux_zero = g_closing > 0
        ax.add_patch(patches.Polygon(tri, facecolor='lightcyan' if flux_zero else 'lightpink', alpha=0.5, zorder=0))
        ax.annotate(0 if flux_zero else r'$\pi$', sum(tri) / 3, size=14)

    ax.axis("equal")
    ax.axis("off")

    if created_fig:
        fig.tight_layout()

    return ax
