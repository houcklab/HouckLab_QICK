from WorkingProjects.Triangle_Lattice_tProcV2.Helpers.Device_calibration.qt_qubit_sys import *
from scipy.optimize import minimize, root_scalar
from matplotlib import patches
# disentangles qubit frequencies

'''Joshua's code for converting dressed to bare frequencies and back again. Last updated 7/25/25'''

def get_bare_freq(dressed_qubit_freq, bare_coupler_freqs, betas):
    '''Dressed qubit frequency + bare coupler frequencies ----> bare qubit frequency'''

    # The index of the qubit frequency in a list of ascending eigenenergies
    # print(dressed_qubit_freq, bare_coupler_freqs)
    qubit_index = np.argsort(np.argsort(np.concatenate([[dressed_qubit_freq], bare_coupler_freqs])))[0]

    def cost(bare_qubit_freq):
        all_freqs = np.concatenate([bare_qubit_freq, bare_coupler_freqs])

        couplings = {(1,j+1+1):betas[j]*np.sqrt(bare_qubit_freq*bare_coupler_freqs[j]) for j in range(len(bare_coupler_freqs))}
        # print(couplings)
        sys = M_qubit_sys(w=all_freqs, U = [0.180]*len(all_freqs),
                        couplings = couplings,
                                    RWA=True, N=3, verbose=False)
        
        found_dressed_freq = sys.energies(1)[qubit_index]

        return (found_dressed_freq - dressed_qubit_freq)**2
    
    bare_qubit_freq = minimize(cost, dressed_qubit_freq).x[0]
    
    
    return bare_qubit_freq

def get_dressed_freq(bare_qubit_freq, bare_coupler_freqs, betas=None, gs=None):
    '''bare qubit frequency + bare coupler frequencies ----> dressed qubit frequency'''
    assert betas is None or gs is None, "Can't pass in both betas and g's"

    # Check if using MHz or GHz
    if bare_qubit_freq > 1000:
        U = 180.
    else:
        U = 0.180


    all_freqs = [bare_qubit_freq] + bare_coupler_freqs
    # The index of the qubit frequency in a list of ascending eigenenergies
    qubit_index = np.argsort(np.argsort(all_freqs))[0]

    if betas is None:
        couplings = {(1,j+1+1):gs[j] for j in range(len(bare_coupler_freqs))}
    else:
        couplings = {(1,j+1+1):betas[j]*np.sqrt(bare_qubit_freq*bare_coupler_freqs[j]) for j in range(len(bare_coupler_freqs))}

    # print(all_freqs)
    sys = M_qubit_sys(all_freqs, U = [U]*len(all_freqs),
                    couplings = couplings,
                                RWA=True, N=3, verbose=False)
    
    found_dressed_freq = sys.energies(1)[qubit_index]

    return found_dressed_freq

    
def bare_system(qubit_freqs, beta_matrix, plot=True):
    '''Hardcoded for our 8 qubit 6 coupler system
        Args: qubit_freqs (14,)
              beta_matrix (14,14)
        Returns: qubit_freqs (14,)
                 g_matrix (14,)'''
    assert np.all(np.abs(beta_matrix-beta_matrix.T) < 1e-8), "Coupling matrix must be symmetric!"

    ### coupling_strength matrix, g_ij = β_ij * sqrt(ω_i * ω_j)
    g_matrix = beta_matrix * np.sqrt(np.outer(qubit_freqs, qubit_freqs))

    if plot: # Only plotting. No calculation
        fig, ax = plt.subplots(figsize=(12,5)) # note we must use plt.subplots, not plt.subplot
    
        QUBIT_SPACING_X = 0.25
        QUBIT_OFFSET_Y = -0.25 * np.sqrt(2)
        QUBIT_OFFSET_X = QUBIT_SPACING_X
        Q1_ORIGIN = np.array((0.225, 0.4))
        
        TOP = [Q1_ORIGIN + (j*QUBIT_SPACING_X,                               0) for j in range(7)]
        BOT = [Q1_ORIGIN + (j*QUBIT_SPACING_X + QUBIT_OFFSET_X, QUBIT_OFFSET_Y) for j in range(7)]
    
        # Ordered in [Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, C1, C2, C3, C4, C5, C6]
        coords = [(TOP+BOT)[j] for j in (0, 7, 2, 9, 4, 11, 6, 13, 1, 8, 3, 10, 5, 12)]
    
    
        for j, coord in enumerate(coords):
            if j < 8:
                # Qubit: Red circle
                patch = plt.Circle(coord, 0.04, edgecolor='maroon', facecolor='indianred',zorder=10, lw=2)
            else:
                # Coupler: Blue triangle
                patch = patches.RegularPolygon(coord, 3, radius=0.04, edgecolor='darkblue', facecolor='cornflowerblue', zorder=10,lw=2)
            ax.add_patch(patch)
            if j < 8 :
                fc, ec = "pink", "maroon"
            else:
                fc, ec = "lightblue", "steelblue"
            # Qubit/coupler frequency box
            ax.annotate(np.round(qubit_freqs[j],1), coord + (-0.04,(-1)**(j)*0.09 - 0.007),
                       bbox=dict(boxstyle="round,pad=0.4",
                          fc=fc, ec=ec, lw=2),zorder=11)
        
        for i, j in zip(*np.nonzero(beta_matrix)):
            if i < j: # Symmetric matrix, so skip repeats
                g = g_matrix[i,j]
                location = (coords[i] + coords[j]) / 2
                
                if j- i !=2:
                    # Qubit-qubit direct coupling over a coupler)
                    path = patches.ConnectionPatch(xyA=coords[i], coordsA=ax.transData, xyB=coords[j], lw=1)
                    ax.add_patch(path)
                    
                    ax.annotate(np.round(g,1), location + (-0.03, 0),
                       bbox=dict(boxstyle="round,pad=0.4",
                          fc="xkcd:pale turquoise", ec="xkcd:sea", lw=2))
                    
    
                else:
                    # Smaller direct couplings, e.g. Q1-Q3 direct coupling
                    ARC_HEIGHT = 0.2
                    theta1 = 0 if i % 2 == 0 else 180
                    path = patches.Arc(location,  np.abs(coords[j] - coords[i])[0], ARC_HEIGHT*2,theta1=theta1, theta2= theta1+180)
                    ax.add_patch(path)
                    ax.annotate(np.round(g,1), location + (-0.03, ARC_HEIGHT * (1 if i%2==0 else -1)),
                       bbox=dict(boxstyle="round,pad=0.4",
                          fc="xkcd:pale turquoise", ec="xkcd:sea", lw=2))
                    
        ax.axis("equal")
        ax.axis("off")
        plt.show(block=False)

    return qubit_freqs, g_matrix


def signed_eff_g(w1, w2, wc, g1, g2, g12):
    Δ1, Δ2 = w1 - wc, w2 - wc
    Σ1, Σ2 = w1 + wc, w2 + wc
    return - ( g1*g2/2*(1/Δ1 + 1/Δ2 - 1/Σ1 - 1/Σ2) + g1*g2*2/wc ) + g12

def invert_eff_g(g_eff, w1, w2, beta1, beta2, beta12, bounds=(0,10000)):
    '''g_eff ---> coupler frequency'''
    g12 = beta12*np.sqrt(w1*w2)
    func = lambda wc: (signed_eff_g(w1, w2, wc, beta1*np.sqrt(w1*wc),  beta2*np.sqrt(w2*wc), g12) - g_eff)**2
    guess = (w1+w2)/2 - beta1*beta2*w1*w2/(-g_eff - g12)
    return minimize(func, x0=guess, bounds=[bounds]).x


def dressed_freqs_to_bare_freqs(qubit_freqs, coupler_freqs, beta_matrix):
    '''Args:
        qubit_freqs: (8,) dressed frequencies
        coupler_freqs: (6,), coupler frequencies
        beta_matrix: (14,14)

        returns:
        bare_freqs: (14,) bare frequencies and coupler frequencies
    '''

    new_qubit_freqs = []
    for q in range(8):
        couplers = np.nonzero(beta_matrix[q, 8:])[0] + 0
        # print(couplers)
        new_qubit_freqs.append(get_bare_freq(qubit_freqs[q], [coupler_freqs[c] for c in couplers], betas= [beta_matrix[q, c+8] for c in couplers]))

    return np.concatenate([new_qubit_freqs, coupler_freqs])

def dressed_to_bare_sys(qubit_freqs, tunable_couplings, beta_matrix):
    '''Args:
        qubit_freqs: (8,) dressed frequencies
        tunable_couplings: (6,), coupling strengths, ordered by C1, C2, C3, C4, C5, C6 legs
        beta_matrix: (14,14)

        returns:
        bare_freqs: (14,) bare frequencies and coupler frequencies
    '''
    coupler_freqs = []
    for j, coupling in enumerate(tunable_couplings):
        if coupling == 0 or coupling > 50:
            # I assume you passed in a frequency (MHz) instead. 
            coupler_freqs.append(coupling)
        else:
            freq = invert_eff_g(tunable_couplings[j], qubit_freqs[j], qubit_freqs[j+2],
                                  beta_matrix[j,j+8], beta_matrix[j+2,j+8], beta_matrix[j,j+2])[0]
            coupler_freqs.append(freq)
    print(coupler_freqs)

    new_qubit_freqs = []
    for q in range(8):
        couplers = np.nonzero(beta_matrix[q, 8:])[0] + 0
        # print(couplers)
        new_qubit_freqs.append(get_bare_freq(qubit_freqs[q], [coupler_freqs[c] for c in couplers], betas= [beta_matrix[q, c+8] for c in couplers]))

    return np.array(new_qubit_freqs + coupler_freqs)


def dress_system(qubit_freqs, beta_matrix=None, g_matrix=None,  plot=True):
    '''Args:
            qubit_freqs: (14,) bare frequencies
           g_matrix: (14,14) matrix of coupling strengths
       
       returns:
           qubit_freqs: (8,) dressed frequencies
           g_matrix: (8, 8), effective coupling strengths
    '''
    # N = 8
    if g_matrix is None:
        g_matrix = beta_matrix * np.sqrt(np.outer(qubit_freqs, qubit_freqs))
    
    new_g_matrix = np.copy(g_matrix[:8,:8])
    for coupler in range(8, 14):
        q1, q2 = np.nonzero(g_matrix[coupler])[0]

        eff_g = signed_eff_g(qubit_freqs[q1], qubit_freqs[q2], qubit_freqs[coupler], g_matrix[q1, coupler], g_matrix[q2, coupler], g_matrix[q1,q2])
        new_g_matrix[q1, q2] = eff_g
        new_g_matrix[q2, q1] = eff_g

    new_qubit_freqs = np.zeros(8)
    for qubit in range(8):
        couplers = np.nonzero(g_matrix[qubit, 8:])[0] + 8
        new_qubit_freqs[qubit] = get_dressed_freq(qubit_freqs[qubit], [qubit_freqs[c] for c in couplers], gs= [g_matrix[qubit, c] for c in couplers])

    if plot:
        plot_dressed_system(new_qubit_freqs, new_g_matrix)
        
    return new_qubit_freqs, new_g_matrix

def plot_dressed_system(qubit_freqs, g_matrix, ax=None):
    """Hardcoded for our 8 qubit system.

    Args:
        qubit_freqs: (8,) array of dressed qubit frequencies
        g_matrix:    (8, 8) effective coupling strengths
        ax:          optional matplotlib Axes to draw into. If None, a new
                     figure+axes are created and returned.
    """
    created_fig = False
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 5))  # standalone usage
        created_fig = True
    else:
        fig = ax.figure

    QUBIT_SPACING_X = 0.25
    QUBIT_OFFSET_Y = -0.25 / np.sqrt(2)
    QUBIT_OFFSET_X = QUBIT_SPACING_X / 2
    Q1_ORIGIN = np.array((0.225, 0.4))

    TOP = [Q1_ORIGIN + (j * QUBIT_SPACING_X, 0) for j in range(4)]
    BOT = [
        Q1_ORIGIN + (j * QUBIT_SPACING_X + QUBIT_OFFSET_X, QUBIT_OFFSET_Y)
        for j in range(4)
    ]

    # Ordered in [Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8]
    coords = [(TOP + BOT)[j] for j in (0, 4, 1, 5, 2, 6, 3, 7)]

    for j, coord in enumerate(coords):

        if j < 8:
            # Qubit: Red circle
            patch = plt.Circle(coord, 0.04, edgecolor='maroon', facecolor='indianred', zorder=10, lw=2)
            ax.text(coord[0], coord[1], f"Q{j+1}", ha='center', va='center', fontsize=8, color='white', zorder=11
            )
        else:
            # Coupler: Blue triangle
            patch = patches.RegularPolygon(coord, 3, radius=0.04, edgecolor='darkblue', facecolor='cornflowerblue',
                                           zorder=10, lw=2)
        ax.add_patch(patch)
        if j < 8:
            fc, ec = "pink", "maroon"
        else:
            fc, ec = "lightblue", "steelblue"
        # Qubit/coupler frequency box
        ax.annotate(np.round(qubit_freqs[j], 1), coord + (-0.04, (-1) ** (j) * 0.09 - 0.007),
                    bbox=dict(boxstyle="round,pad=0.4",
                              fc=fc, ec=ec, lw=2), zorder=11)

    for i, j in zip(*np.nonzero(g_matrix[:8, :8])):
        if i < j:  # Symmetric matrix, so skip repeats
            g = g_matrix[i, j]
            location = (coords[i] + coords[j]) / 2

            # Coupling > 3 MHz (all neighbor couplings)
            path = patches.ConnectionPatch(xyA=coords[i], coordsA=ax.transData, xyB=coords[j], lw=1)
            ax.add_patch(path)

            ax.annotate(np.round(g, 1), location + (-0.01, 0),
                        bbox=dict(boxstyle="round,pad=0.4",
                                  fc="xkcd:pale turquoise" if g > 0 else "xkcd:pale lavender",
                                  ec="xkcd:sea" if g > 0 else "xkcd:periwinkle", lw=2))

    # 0 or Pi fluxes
    for i, j, k in [np.array([0, 1, 2]) + j for j in range(6)]:
        a, b, c = [coords[x] for x in (i, j, k)]

        flux = 0 if g_matrix[i, k] > 0 else 1

        tri = patches.Polygon([a, b, c], facecolor='lightcyan' if flux == 0 else 'lightpink', alpha=0.5, zorder=0)
        center = (a + b + c) / 3

        ax.annotate(0 if flux == 0 else r'$\pi$', center, size=14)
        # ax.annotate(r'$\pi$', center, size=14)
        ax.add_patch(tri)

    ax.axis("equal")
    ax.axis("off")

    if created_fig:
        fig.tight_layout()

    return ax

