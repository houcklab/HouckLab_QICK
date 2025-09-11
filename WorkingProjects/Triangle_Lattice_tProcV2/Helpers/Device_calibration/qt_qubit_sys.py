'''Joshua's personal code for qutip simulations, used for full_device_calib. Last updated 7/25/25 '''

import matplotlib.pyplot as plt
import qutip as qt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from tqdm.notebook import tqdm
from scipy.optimize import curve_fit
from time import time 
from functools import lru_cache

_2pi = 2*np.pi
_2PI = 2*np.pi
TAU = 2*np.pi

    

class M_qubit_sys():
    def __init__(self, w, U, couplings, time_deps={}, T1s=None, T2s=None, RWA=True, N=3, verbose=True):
        '''Initializes an M-qubit system.
        args: w: list of M bare frequencies (GHz)
              U: list of M anharmonicities (GHz). time-dependence of U currently not supported.
              couplings: dict, {(i,j} : kij}, where i and j are qubit int labels (1-indexed) and kij is the coupling strength (GHz)
              time_deps: dict, {i or (i,j) : lambda t}, where the lambda gives a time-dependence (ns to GHz) for the particular qubit w or coupling kij
              T1s: list of M T1s (ns), or None. [1, None] -> qubit 2 has no decay.
              T2s: list of M T2s (ns), or None. [1, None] -> qubit 2 has no decay.
              RWA: Whether or not to take the rotating wave approximation
              N: int, number of Fock states. 3 is usually sufficient.
              verbose: print computation time when diagonalizing Hamiltonian
              reduce_Hamil_to_n: None or int. if int, reduce the Hamiltonian to the n-particle subspace.
        Attributes:
            n_ops:    list of M number operators, pass into e_ops
            H_static: non-time-dependent Hamiltonian, units of 2π/ns
            H_time_dep : time-dependent Hamiltonian, time units are ns
        '''
        self.verbose = verbose

        M = len(w)
        assert len(w) == len(U)
        
        w = np.insert(w, 0, None) # So we can 1-index
        U = np.insert(U, 0, None) # So we can 1-index
        self.w = w
        self.U = U
        self.couplings = couplings
        self.time_deps = time_deps
        self.N = N
        self.M = M

        I = qt.qeye(N)
        create = qt.create(N)
        destroy = qt.destroy(N)
        num = qt.num(N)

        a = {}
        ad = {}
        n_ops = {}
        
        H_static = 0
        H_time_dep = []

        # Everything will be 1-indexed from now on (except IxM)
        IxM = [I]*M

        # Create single-qubit Hamiltonians
        for i in range(1, M+1):
             # annihilation operator
            _a = IxM.copy()
            _a[i-1] = destroy
            a[i] = qt.tensor(*_a)
             # creation operator
            _ad = IxM.copy()
            _ad[i-1] = create
            ad[i] = qt.tensor(*_ad)
            # number operator
            _n_op = IxM.copy()
            _n_op[i-1] = num
            n_ops[i] = qt.tensor(*_n_op)
    
            # qubit Hamiltonian: ω * ad*a - U/2 * ad*a(ad*a - 1)
            H_static += _2PI*w[i] * ad[i]*a[i] - _2PI*U[i]/2 * (ad[i]*a[i])*(ad[i]*a[i] - 1)
            
            if i in time_deps:
                H_time_dep.append([_2PI*ad[i]*a[i], time_deps[i]])
                H_time_dep.append(-_2PI*U[i]/2 * (ad[i]*a[i])*(ad[i]*a[i] - 1))
            else:
                H_time_dep.append(_2PI*w[i] * ad[i]*a[i] - _2PI*U[i]/2 * (ad[i]*a[i])*(ad[i]*a[i] - 1))

        # Create coupling Hamiltonians
        for (i, j), kij in couplings.items():
            if RWA:
                exchange_op = _2PI * (a[i]*ad[j] + ad[i]*a[j])
            else:
                exchange_op = _2PI * (a[i] + ad[i]) * (a[j] + ad[j]) # * np.sqrt(w[i] * w[j])

            H_static += kij * exchange_op
            if (i, j) in time_deps:
                H_time_dep.append([exchange_op, time_deps[(i,j)]])
            else:
                H_time_dep.append(kij * exchange_op)

        # Create collapse operators
        T1s = [None]*M if T1s is None else T1s
        T1s = np.insert(T1s, 0, None) # So we can 1-index
        # T1 Relaxation
        c_ops = [np.sqrt(1/T1s[j])*a[j] for j in range(1,M+1) if T1s[j] is not None]
        # Implement dephasing if N = 2
        if N == 2:
            T2s = [None]*M if T2s is None else T2s
            T2s = np.insert(T2s, 0, None) # So we can 1-index
            for j in range(1, M+1):
                if T2s[j] is not None:
                    _z = IxM.copy()
                    _z[j-1] = qt.sigmaz()
                    z = qt.tensor(*_z)
                    gamma = 1/T2s[j] - 1/(2*T1s[j]) # = 1/Tphi
                    c_ops.append(np.sqrt(gamma/2)*z)
        elif T2s is not None:
            print("T2 list was given but N != 2, did you mean to set N=2?")
            
        self.c_ops = c_ops               

        # 1-indexed        
        self.a = a
        self.ad = ad
        self.n_ops = n_ops

        self.H_static = H_static
        self.H_time_dep = H_time_dep

        # 0 indexed
        self.num_ops = [self.n_ops[k] for k in sorted(self.n_ops)]

        self.diagonalized = False
            
    def plot_energies(self, tlist):
        '''plot all qubit energies'''
        for j in range(1, self.M+1):
            if j in self.time_deps:
                plt.plot(tlist+0.005*tlist[-1]*j, self.time_deps[j](tlist), label=f"Qubit {j}")
            else:
                plt.plot(tlist+0.005*tlist[-1]*j, np.full(tlist.shape, self.w[j]), label=f"Qubit {j}")
        plt.legend()
        plt.ylabel("Detuning (GHz)")
        plt.xlabel("Time (ns)")
        plt.title("Qubit Frequencies versus Time")
        plt.show()

    # @lru_cache
    def diagonalize(self, n=None):
        # Cache this so we don't rerun it every time
        if not self.diagonalized:
            start = time()
            self.diagonalization_cache = self.H_static.eigenstates()
            self.diagonalized = True
            if self.verbose:
                print(fr"Hamiltonian of shape {self.H_static.shape} took {time()-start} seconds to diagonalize.")

        energies, states = self.diagonalization_cache   
        energies = energies / _2PI

        if n is None:
            return energies, states
        else: # Return only energies and states with such a particle number
            index_mask = (np.round(np.array([np.sum(qt.expect(self.num_ops, state)) for state in states]),0)) == n
            return energies[index_mask], states[index_mask]

    def energies(self, n=None):
        '''returns: eigenenergies of the static Hamiltonian in units of GHz, where vacuum has E=0.
        Args:
            n:  if None, return all eigenstates.
                if int, return the n-particle eigenstates.'''
        return self.diagonalize(n)[0]

    def eigstates(self, n=None):
        '''Return eigenstates (Qobj) of the static Hamiltonian.
        Args:
            n:  if None, return all eigenstates.
                if int, return the n-particle eigenstates.
                (Eigenstates have definite particle number only under the RWA. If the RWA is not used, then particle occupations of
                eigenstates are rounded to the nearest integer.'''
        return self.diagonalize(n)[1]

    def Jhat(self, q1, q2, J_factor = False):
        '''Returns the current operator j_{q1->q2}. Natural units (no 2π factor)!!!
        Args: q1, q2: qubit indices (1-indexed)'''
        try:
            J_strength = self.couplings[(q1,q2)]
        except:
            J_strength = self.couplings[(q2,q1)]
        
        if not J_factor:
            J_strength = 1
        
        
        return 1j*(J_strength* self.ad[q1]*self.a[q2] - np.conjugate(J_strength) * self.ad[q2]*self.a[q1])
        
    def Jcorr(self, q1_q2, q3_q4):
        return self.Jhat(*(q1_q2)) * self.Jhat(*(q3_q4))
    
    
        
    def plot_occupations(self, n, num_states=np.inf):
        '''Plot the occupation levels of a certain particle-state manifold of the static Hamiltonian.
        Args:
            n: total occupation number of the eigenstates to plot.
        '''
        eigstates_n = self.eigstates(n)
        Erange = range(0, min(len(eigstates_n), num_states))
        qlist = range(1, self.M+1) # 1, 2 ,3
        for i in Erange:
            # plt.ylim(0,0.6)
            #color=(0.10588235294117647, 0.6196078431372549,0.4666666666666667))#
            print(qt.expect(self.num_ops, eigstates_n[i]))
            bars = plt.bar(qlist, qt.expect(self.num_ops, eigstates_n[i]), color= plt.rcParams['axes.prop_cycle'].by_key()['color'])
            for bar in bars:
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
            plt.xticks(qlist)
            plt.xlabel("Qubit")
            plt.ylabel("Occupation")
            plt.title(f"State {i}, n={n}: E = {np.round(self.energies(n)[i]*1000,1)} MHz")
            plt.show()

    def mesolve(self, psi0, tlist, plot = True, title=None, labels=None, e_ops=None, ylabel=None, **kwargs):
        if labels is None:
            labels = [f"Qubit {i+1}" for i in range(self.M)]
        if e_ops is None:
            e_ops = self.num_ops
            ylabel = "Site occupation"
        
        start = time()
        res = qt.mesolve(self.H_time_dep, psi0.unit(), tlist, c_ops=self.c_ops, e_ops=e_ops, **kwargs)#, options=qt.solver.Options(nsteps=7000))
        print(fr"{len(tlist)} time steps for {self.M} qubits and N={self.N} took {time()-start} seconds to simulate.")
        if plot:
            for i in range(len(res.expect)):
                plt.plot(tlist+0.005*tlist[-1]*i, res.expect[i], label = labels[i])         # (Offset tlist when plotting to see overlapping lines)

            if title is not None:
                plt.title(title)
            plt.xlabel("Time (ns)")
            plt.ylabel(ylabel)
            plt.legend()
            plt.show()
            

        return res
    
    def add_drive(self, qubit_num, Ω, ω_GHz, envelope=None):
        if envelope is None: envelope = lambda t: 1

        self.H_time_dep.append([_2PI*        Ω/2 *self.ad[qubit_num], lambda t: np.exp(-1j*_2PI*ω_GHz*t) * envelope(t)])
        self.H_time_dep.append([_2PI*np.conj(Ω/2)* self.a[qubit_num], lambda t: np.exp(+1j*_2PI*ω_GHz*t) * envelope(t)])


class M_qubit_sys_reduced(M_qubit_sys):
    def __init__(self, w, U, couplings, time_deps={}, T1s=None, T2s=None, RWA=True, N=3, reduce_Hamil_to_n=None):
        '''Initializes an M-qubit system.
        args: w: list of M bare frequencies (GHz)
              U: list of M anharmonicities (GHz). time-dependence of U currently not supported.
              couplings: dict, {(i,j} : kij}, where i and j are qubit int labels (1-indexed) and kij is the coupling strength (GHz)
              time_deps: dict, {i or (i,j) : lambda t}, where the lambda gives a time-dependence (ns to GHz) for the particular qubit w or coupling kij
              T1s: list of M T1s (ns), or None. [1, None] -> qubit 2 has no decay.
              T2s: list of M T2s (ns), or None. [1, None] -> qubit 2 has no decay.
              RWA: Whether or not to take the rotating wave approximation
              N: int, number of Fock states. 3 is usually sufficient.
              reduce_Hamil_to_n: None or int. if int, reduce the Hamiltonian to the n-particle subspace.
        Attributes:
            n_ops:    list of M number operators, pass into e_ops
            H_static: non-time-dependent Hamiltonian, units of 2π/ns
            H_time_dep : time-dependent Hamiltonian, time units are ns
        '''
        super().__init__(w, U, couplings, time_deps, T1s, T2s, RWA, N)
        occupation_list = sum(self.num_ops).diag()
        self.indices_n = np.nonzero(occupation_list == reduce_Hamil_to_n)[0]
        
        self.reduce_Hamiltonian_to_num(reduce_Hamil_to_n)

    @lru_cache
    def extract_states(self, oper):
        return qt.Qobj(oper.to("CSR").data_as("csr_matrix")[self.indices_n, :][:, self.indices_n])
    
    def Jcorr(self, q1_q2, q3_q4):
        return self.extract_states(super().Jcorr(q1_q2, q3_q4))
    
    def reduce_Hamiltonian_to_num(self, n):
        '''Reduce the Hamiltonians to be limited to the particular number subspace'''

        print(f"Reduced {self.H_static.shape[0]}^2-dimensional subspace to a {len(self.indices_n)}^2-dimensional one.")

        self.H_static = self.extract_states(self.H_static)
        for j in range(len(self.H_time_dep)):
            if isinstance(self.H_time_dep[j], list):
                self.H_time_dep[j][0] = self.extract_states(self.H_time_dep[j][0])
            else:
                self.H_time_dep[j] = self.extract_states(self.H_time_dep[j])
        self.num_ops = [self.extract_states(num) for num in self.num_ops]

        self.diagonalized = False

def lin(start, end, start_time=0, end_time = 1):
    assert end_time > start_time
    def qubit_ramp(t, *args):
        '''bring qubit from freq start at start_time to freq end at end_time'''
        span = end_time - start_time
        return np.heaviside(t-end_time, 0.5) * end + \
               np.heaviside(-(t-start_time), 0.5) * start + \
               np.heaviside(-(t-end_time),0.5) * np.heaviside(t-start_time, 0.5) * (start*(1-(t-start_time)/span) + end*(t-start_time)/span)
    return qubit_ramp

from scipy.interpolate import CubicSpline, PchipInterpolator, Akima1DInterpolator

def exp_ramp(t_pts, freq_pts, taus):
    '''t_pts: time points
       freq_pts: frequency at each time point
       taus: exponential time constant of the length of each interval'''
    t_pts = np.asarray(t_pts)
    freq_pts = np.asarray(freq_pts)
    taus = np.asarray(taus)
    def ii(t):
        return np.searchsorted(t_pts, t)

    def func(t):
        _ii = np.searchsorted(t_pts, t)  # interval index
        res = np.piecewise(t, condlist=[_ii==0, _ii==len(t_pts)],
                     funclist=[freq_pts[0], freq_pts[-1],
                               lambda t: freq_pts[ii(t)-1] + (freq_pts[ii(t)]-freq_pts[ii(t)-1]) \
                               * (np.exp(-(t-t_pts[ii(t)-1]) / (t_pts[ii(t)] - t_pts[ii(t)-1]) * taus[ii(t)-1]) -1) \
                               / (np.exp(-taus[ii(t)-1]) - 1)
                               ])
        return res.item() if not res.shape else res
    
    return func

def cubic_ramp(t_pts, freq_pts, signs):
    '''t_pts: time points
       freq_pts: frequency at each time point
       taus: exponential time constant of the length of each interval'''
    t_pts = np.asarray(t_pts)
    freq_pts = np.asarray(freq_pts)
    signs = np.sign(signs)

    def func(t):
        i = np.searchsorted(t_pts, t)  # interval index
        if i == 0:
            return freq_pts[0]
        elif i == len(freq_pts):
            return freq_pts[-1]
        elif signs[i-1] > 0:  # 1
            return freq_pts[i-1] + (freq_pts[i]-freq_pts[i-1])*((t-t_pts[i-1])/(t_pts[i]-t_pts[i-1]))**3
        else:
            return freq_pts[i] + (freq_pts[i-1]-freq_pts[i])*(1-(t-t_pts[i-1])/(t_pts[i]-t_pts[i-1]))**3

    def f(t):
        try:
            return np.array([func(tt) for tt in t])
        except:
            return func(t)
        
    return f

def generate_cubic_ramp(initial_gain, final_gain, ramp_duration, ramp_start_time=0, reverse=False):
    '''
    Creates a cubic ramp starting from initial gain at t = ramp_start_time ending at final gain at t = ramp_start_time
    + ramp_duration
    :param initial_gain: gain of ramp for t <= ramp_start_time
    :param final_gain: gain of ramp for t >= ramp_start_time + ramp_duration
    :param ramp_duration: total time to ramp between initial_gain and final_gain in clock cycles (2.32/16 ns)
    :param ramp_start_time: start time for ramp in clock cycles (2.32/16 ns)
    :param reverse: if False (default), the ramp becomes flatter closer to final_gain at t =  ramp_start_time + ramp_duration
                    if True, the ramp is flat at the beginning and becomes steeper at the end
    '''

    if ramp_start_time < 0:
        raise ValueError(f'ramp_start_time must be positive, given: {ramp_start_time}')

    if ramp_duration < 0:
        raise ValueError(f'ramp_duration must be positive, given: {ramp_duration}')

    total_duration = int(ramp_start_time + ramp_duration) + 1
    gains = np.zeros(total_duration)

    for i in range(total_duration):
        if reverse:
            if i <= ramp_start_time:
                gains[i] = initial_gain
            elif i <= ramp_start_time + ramp_duration:
                t = i - ramp_start_time
                gains[i] = (final_gain - initial_gain) * np.power(t / ramp_duration, 3) + initial_gain
            else:
                gains[i] = final_gain
        else:
            if i <= ramp_start_time:
                gains[i] = initial_gain
            elif i <= ramp_start_time + ramp_duration:
                t = i - ramp_start_time - ramp_duration
                gains[i] = (final_gain - initial_gain) * np.power(t / ramp_duration, 3) + final_gain
            else:
                gains[i] = final_gain

    return gains

def lambda_ramp(t_pts, freq_pts, interpolator = 'linear'):
    if interpolator == 'linear':
        return lambda t, *args: np.interp(t, t_pts, freq_pts)
    
    elif interpolator == 'cubic':
        interp_func = CubicSpline(t_pts, freq_pts)
    elif interpolator == 'pchip':
        interp_func = PchipInterpolator(t_pts, freq_pts)
    elif interpolator == 'akima':
        interp_func = Akima1DInterpolator(t_pts, freq_pts)
    elif interpolator == 'makima':
        interp_func = Akima1DInterpolator(t_pts, freq_pts, method='makima')
    else:
        raise Exception("interpolator argument needs to be 'linear', 'cubic', 'pchip', 'akima', or 'makima'.")
    
    return interp_func

