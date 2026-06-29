'''
A diagonalization helper purely for finding dressed frequencies of qubits.
Pasted directly from my (Joshua Wang's) own qutip code, so contains a lot of other things
that aren't needed. (05/19/2026) 
'''


import matplotlib.pyplot as plt
import qutip as qt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from tqdm.notebook import tqdm
from scipy.optimize import curve_fit
from time import time 
from functools import lru_cache
from fractions import Fraction
import itertools
import bezier

_2pi = 2*np.pi
_2PI = 2*np.pi
TAU = 2*np.pi

def ncorr_label(pair1, pair2):
    return rf"$\langle \hat{{n}}_{{{''.join(str(i) for i in pair1)}}} ~\hat{{n}}_{{{''.join(str(i) for i in pair2)}}} \rangle$"

def jcorr_label(pair1, pair2):
    return rf"$\langle \hat{{J}}_{{{''.join(str(i) for i in pair1)}}} ~\hat{{J}}_{{{''.join(str(i) for i in pair2)}}} \rangle$"


class M_qubit_sys():
    def __init__(self, w, U, couplings={}, time_deps={}, T1s=None, T2s=None, RWA=True, N=3, verbose=True):
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
            num_ops: 0-indexed list of M number operators, also reduced if applicable
            H_static: non-time-dependent Hamiltonian, units of 2π/ns
            H_time_dep : time-dependent Hamiltonian, time units are ns
        '''
        self.verbose = verbose

        M = len(w)
        assert len(w) == len(U)
        
        w = np.asarray(w, dtype=float)
        U = np.asarray(U, dtype=float)
        w = np.insert(w, 0, None) # So we can 1-index
        U = np.insert(U, 0, None) # So we can 1-index
        self.w = w
        self.U = U

        self.couplings = couplings
        self.time_deps = time_deps

        if hasattr(N, '__iter__'):
            self.N = list(N)
        else:
            self.N = [N]*M
        self.M = M
        self.RWA = RWA

        
        

        a = {}
        ad = {}
        n_ops = {}
        
        H_static = 0
        H_time_dep = []

        # Everything will be 1-indexed from now on (except IxM)
        IxM = [qt.qeye(_N) for _N in self.N]

        # Create single-qubit Hamiltonians
        for i in range(1, M+1):
            _N = self.N[i-1]
            create = qt.create(_N)
            destroy = qt.destroy(_N)
            num = qt.num(_N)
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
        # Implement dephasing
        T2s = [None]*M if T2s is None else T2s
        T2s = np.insert(T2s, 0, None) # So we can 1-index
        for j in range(1, M+1):
            if T2s[j] is not None:
                gamma = 1/T2s[j] - (1/(2*T1s[j]) if T1s[j] is not None else 0) # = 1/Tphi
                c_ops.append(np.sqrt(gamma/2)*2*n_ops[j]) #sqrt(gamma/2)*sigmaz, but sigmaz = 2*n - I, and I doesn't do anything in Lindblad
            
        self.c_ops = c_ops               

        # 1-indexed (technically dicts)
        self.a = a
        self.ad = ad
        self.n_ops = n_ops

        self.H_static = H_static
        self.H_time_dep = H_time_dep

        # 0 indexed n_ops, for use in a single list
        self.num_ops = [self.n_ops[k] for k in sorted(self.n_ops)]

        self.diagonalized = False
    
    def plot_connectivity(self):
        """
        Visualizes the system topology. 
        Nodes: Labeled with (Index, Frequency). Color shows frequency scale.
        Edges: Labeled with Coupling Strength (GHz).
        """
        import networkx as nx
        import matplotlib.pyplot as plt

        G = nx.Graph()
        G.add_nodes_from(range(1, self.M + 1))
        
        # 1. Create Node Labels (Index + Frequency)
        # self.w is 1-indexed based on your __init__
        node_labels = {i: f"Q{i}\n{self.w[i]:.2f} GHz" for i in range(1, self.M + 1)}
        
        # 2. Create Edge Labels (Couplings)
        edge_labels = {}
        for (i, j), kij in self.couplings.items():
            G.add_edge(i, j)
            edge_labels[(i, j)] = f"{kij*1000:.1f} MHz" # MHz often easier to read for kij

        # 3. Frequency-based coloring
        freqs = [self.w[i] for i in range(1, self.M + 1)]
        
        # 4. Layout and Drawing
        pos = nx.spring_layout(G)
        plt.figure(figsize=(10, 7))
        
        nodes = nx.draw_networkx_nodes(G, pos, 
                                    node_color=freqs, 
                                    cmap=plt.cm.viridis, 
                                    node_size=1500, 
                                    alpha=0.8)
        
        nx.draw_networkx_edges(G, pos, width=2, edge_color='gray', alpha=0.5)
        nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=10, font_weight='bold')
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color='darkred')

        # Add a colorbar to explain the node colors
        plt.colorbar(nodes, label='Frequency (GHz)')
        plt.title("System Connectivity & Energy Landscape")
        plt.axis('off')
        plt.show()

    def reducible_Qobj(func):
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            # If we are in a reduced system and if result is a Qobj
            if hasattr(self, 'indices_n') and isinstance(result, qt.Qobj):
                return self.extract_states(result)
            
            return result
        return wrapper

    @reducible_Qobj
    def fock(self,n):
        '''Convience function for qt.fock'''
        return qt.fock(self.N, n)
    @reducible_Qobj
    def basis(self,n):
        return self.fock(n)

    # a and ad -> 0 in fixed qubit subspace, so can't use directly on Jhat
    @reducible_Qobj
    def sigmax(self, qubit_num):
        '''Returns the sigmax operator for a particular qubit (1-indexed)'''
        return self.a[qubit_num] + self.ad[qubit_num]
    @reducible_Qobj
    def sigmay(self, qubit_num):
        '''Returns the sigmay operator for a particular qubit (1-indexed)'''
        return -1j*self.a[qubit_num] + 1j*self.ad[qubit_num]
    @reducible_Qobj
    def sigmaz(self, qubit_num):
        '''Returns the sigmaz operator for a particular qubit (1-indexed)'''
        return 2*self.n_ops[qubit_num]# - qt.qeye(self.H_static.shape[0])
    
    def add_drive(self, qubit_num, Ω, ω_GHz, envelope=None):
        if envelope is None: envelope = lambda t: 1

        self.H_time_dep.append([_2PI*        Ω/2 *self.ad[qubit_num], lambda t: np.exp(-1j*_2PI*ω_GHz*t) * envelope(t)])
        self.H_time_dep.append([_2PI*np.conj(Ω/2)* self.a[qubit_num], lambda t: np.exp(+1j*_2PI*ω_GHz*t) * envelope(t)])
        # self.H_time_dep.append([_2PI*        Ω/2 *(self.a[qubit_num]+self.ad[qubit_num]), lambda t: np.cos(_2PI*ω_GHz*t) * envelope(t)])

    def plot_energies(self, tlist, w12 = False):
        '''plot all qubit energies'''
        for j in range(1, self.M+1):
            if w12:
                U = self.U[j]
            else:
                U = 0

            if j in self.time_deps:
                plt.plot(tlist+0.005*tlist[-1]*j, self.time_deps[j](tlist) - U, label=f"Qubit {j}")
            else:
                plt.plot(tlist+0.005*tlist[-1]*j, np.full(tlist.shape, self.w[j]), label=f"Qubit {j}")
        if not w12:
            plt.legend()
        plt.ylabel("Detuning (GHz)")
        plt.xlabel("Time (ns)")
        plt.title("Qubit Frequencies versus Time")
        # plt.show()

    def time_dep_systems(self, tlist):
        '''Generate a list of M_qubit_sys objects with the time-dependent parameters at each time in tlist.
        Args:
            tlist: list of times (ns)
        Returns:
            list of M_qubit_sys objects'''
        if not isinstance(tlist, (list, tuple, np.ndarray)):
            tlist = [tlist]

        for i, t in enumerate(tqdm(tlist)):
            w = np.copy(self.w)
            U = np.copy(self.U)
            couplings = self.couplings.copy()

            for key, time_dep_func in self.time_deps.items():
                if isinstance(key, int):
                    w[key] = time_dep_func(t)
                elif isinstance(key, tuple):
                    couplings[key] = time_dep_func(t)

            if "Hamil_n" in dir(self):
                new_M_qubit_sys = M_qubit_sys_reduced(w[1:], U[1:], couplings, RWA=self.RWA, N=self.N, reduce_Hamil_to_n=self.Hamil_n, verbose=False)
            else:
                new_M_qubit_sys = M_qubit_sys(w[1:], U[1:], couplings, RWA=self.RWA, N=self.N, verbose=False)

            yield new_M_qubit_sys
    
    def system_t0(self):
        '''Return the M_qubit_sys object with the time-dependent parameters at t=0.'''
        return next(self.time_dep_systems(0))

    def time_dep_eigenergies(self, tlist,num_states=0,color=None, plot=True):
        '''Plot the eigenenergies of the time-dependent Hamiltonian versus time.
        Args:
            num_states: maximum number of states to plot.'''

        energies = []
        for i, Qsys in enumerate(self.time_dep_systems(tlist)):
            energies.append(Qsys.energies()[-num_states:])

        energies = np.array(energies)
        if plot:
            for i in range(energies.shape[1]):
                plt.plot(tlist+0.000*tlist[-1]*i, 1000*energies[:,i], color=color)
            # plt.legend()
            plt.ylabel("Energy (MHz)")
            plt.xlabel("Time (ns)")
            # plt.title(f"{'All' if n is None else n}-particle Eigenenergies versus Time")
        return energies
    
    def time_dep_occupations(self, tlist, n, state_idx):
        '''Plot the occupation numbers of the n-particle eigenstates of the time-dependent Hamiltonian versus time.
        Args:
            n: total occupation number of the eigenstates to plot.
            num_states: maximum number of states to plot.'''
        
        occupations = []
        for i, Qsys in enumerate(self.time_dep_systems(tlist)):
            occupations.append(Qsys.occupations(n))

        occupations = np.array(occupations)
        # for i in range(occupations.shape[1]):
        plt.plot(tlist+0.005*tlist[-1]*0, occupations[:,state_idx])
        plt.legend()
        plt.ylabel("Occupation")
        plt.xlabel("Time (ns)")
        plt.title(f"{n}-particle Eigenstate Occupations versus Time")
        return occupations

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

    def dressed_state(self, state, index=None):
        '''Return the dressed state corresponding to a particular fock state.
        Args:
            fock: list of occupation numbers for each qubit. Ex: [1,0,0] for |100>
            index: optional, return indexth-most overlapping state
            '''
        if type(state) is not qt.Qobj:
            state = qt.fock(self.N,state)
        
        state = state.unit()
        number = np.round(np.sum(qt.expect(self.num_ops, state),0))
        # print(number)

        energies, states = self.diagonalize(number)
        overlaps = np.array([np.abs(eigstate.overlap(state)) for eigstate in states])

        if index is None:
            max_idx = np.argmax(overlaps)
        else:
            max_idx = np.argsort(overlaps)[-index]

        return states[max_idx], energies[max_idx]
    
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
        
    def Jcorr(self, *args):
        '''Call as Jcorr((1,2),(3,4)) or Jcorr(1,2,3,4)'''
        if len(args) == 2:
            return self.Jhat(*args[0]) * self.Jhat(*args[1])
        elif len(args) == 4:
            return self.Jhat(args[0], args[1]) * self.Jhat(args[2], args[3])
        else:
            raise ValueError
    
    def KE(self, q1, q2, J_factor = False):
        '''Returns the kinetic energy operator for the coupling between qubits q1 and q2.
        Args: q1, q2: qubit indices (1-indexed)'''
        if not J_factor:
            J_strength = 1
        else:
            try:
                J_strength = self.couplings[(q1,q2)]
            except:
                J_strength = self.couplings[(q2,q1)]
        
        return J_strength * self.ad[q1]*self.a[q2] + np.conjugate(J_strength) * self.ad[q2]*self.a[q1]
    
    def BOI(self):
        op = 0
        for j in range(4,self.M, 2):
            op += self.KE(j-1, j)
            op -= self.KE(j+1, j)

        op = op / (self.M-4)
        return op

    def odlro(self, q1, q2):
        '''Off-diagonal long range order correlator: <a^dagger_q1 a_q2>'''
        return self.ad[q1]*self.a[q2]

    def coherence(self, q1, q2):
        '''another name for the odlro'''
        return self.odlro(q1,q2)

    def occupations(self, n=None, num_states=np.inf):
        '''Return the occupation numbers of the eigenstates with a given particle number.
        Args:
            n: total occupation number of the eigenstates to consider.
        '''
        if num_states == np.inf:
            num_states = len(self.eigstates(n))
        eigstates_n = self.eigstates(n)[:num_states] 
        return [qt.expect(self.num_ops, state) for state in eigstates_n]

    def plot_occupations(self, n, num_states=np.inf):
        '''Plot the occupation levels of a certain particle-state manifold of the static Hamiltonian.
        Args:
            n: total occupation number of the eigenstates to plot.
        '''
        occupations = self.occupations(n)
        Erange = range(0, min(len(occupations), num_states))
        qlist = range(1, self.M+1) # 1, 2 ,3
        for i in Erange:
            # plt.ylim(0,0.6)
            #color=(0.10588235294117647, 0.6196078431372549,0.4666666666666667))#
            idx = -1-i
            bars = plt.bar(qlist, occupations[idx], color= plt.rcParams['axes.prop_cycle'].by_key()['color'])
            for bar in bars:
                plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f'{bar.get_height():.3f}', ha='center', va='bottom', fontsize=12)
            plt.xticks(qlist)
            plt.xlabel("Qubit")
            plt.ylabel("Occupation")
            plt.title(f"State {i}, n={n}: E = {np.round(self.energies(n)[idx]*1000,1)} MHz")
            plt.show()

    def mesolve(self, psi0, tlist, plot = True, title=None, labels=None, e_ops=None, c_ops = None, ylabel=None, **kwargs):
        if e_ops is None:
            e_ops = self.num_ops
            ylabel = "Site occupation"
            if labels is None:
                labels = [f"Qubit {i+1}" for i in range(self.M)]
        else:
            if labels is None:
                labels = [f'e_ops[{i}]' for i in range(len(e_ops))]
        if c_ops is None:
            c_ops = self.c_ops
        start = time()
        res = qt.mesolve(self.H_time_dep, psi0.unit(), tlist, c_ops=c_ops, e_ops=e_ops, **kwargs)#, options=qt.solver.Options(nsteps=7000))
        print(fr"{len(tlist)} time steps for {self.M} qubits and N={self.N} took {time()-start} seconds to simulate.")
        if plot:
            for i in range(len(res.expect)):
                plt.plot(tlist+0.005*tlist[-1]*i, res.expect[i], label = labels[i]) # (Offset tlist when plotting to see overlapping lines)

            if title is not None:
                plt.title(title)
            plt.xlabel("Time (ns)")
            plt.ylabel(ylabel)
            plt.legend()
            # plt.show()
        return res
    
    def mcsolve(self, psi0, tlist, plot = True, title=None, labels=None, e_ops=None, c_ops = None, ylabel=None, **kwargs):
        if e_ops is None:
            e_ops = self.num_ops
            ylabel = "Site occupation"
            if labels is None:
                labels = [f"Qubit {i+1}" for i in range(self.M)]
        else:
            if labels is None:
                labels = [f'e_ops[{i}]' for i in range(len(e_ops))]
        if c_ops is None:
            c_ops = self.c_ops
        start = time()
        res = qt.mcsolve(self.H_time_dep, psi0.unit(), tlist, c_ops=c_ops, e_ops=e_ops, **kwargs)#, options=qt.solver.Options(nsteps=7000))
        print(fr"{len(tlist)} time steps for {self.M} qubits and N={self.N} took {time()-start} seconds to simulate.")
        if plot:
            for i in range(len(res.expect)):
                plt.plot(tlist+0.005*tlist[-1]*i, res.expect[i], label = labels[i]) # (Offset tlist when plotting to see overlapping lines)

            if title is not None:
                plt.title(title)
            plt.xlabel("Time (ns)")
            plt.ylabel(ylabel)
            plt.legend()
            # plt.show()
        return res



    def statistics(self, observable, eigstate_n=None, eigstate_index=-1):
        '''Convenience function for quickly calling qt.measurement.measurement_statistics() on an eigenstate.'''
        stats = qt.measurement.measurement_statistics(self.eigstates(eigstate_n)[eigstate_index], observable)
        return stats[0], stats[2] # eigenvalues, probabilities
    
    def expect(self, observable, eigstate_n=None, eigstate_index=-1):
        '''Convenience function for quickly calling qt.expect() on an eigenstate.'''
        return qt.expect(observable, self.eigstates(eigstate_n)[eigstate_index])
    
    def ncorr(self, *args):
        '''Call as ncorr((1,2),(3,4)) or ncorr(1,2,3,4)'''
        if len(args) == 2:
            n1, n2 = args[0]
            n3, n4 = args[1]
        elif len(args) == 4:
            n1, n2, n3, n4 = args
        else:
            raise ValueError
        return (self.num_ops[n1-1]-self.num_ops[n2-1])*(self.num_ops[n3-1]-self.num_ops[n4-1])

    def ndiff(self, *args):
        '''Call as ncorrelator((1,2),(3,4)) or ncorrelator(1,2,3,4)'''
        if len(args) == 2:
            n1, n2 = args
        elif len(args) == 1:
            n1, n2 = args[0]
        else:
            raise ValueError
        return (self.num_ops[n1-1]-self.num_ops[n2-1])

    def projectors(self):
        projectors = [qt.measurement.measurement_statistics(self.eigstates()[-1], num_op)[1] for num_op in self.num_ops]
        projectors_1 = [proj[1] for proj in projectors] # Projectors onto |1>
        projectors_2 = [proj[2] for proj in projectors] # Projectors onto |2>
        return projectors_1, projectors_2

    def partition_compressed(self, eigstates):
        '''partitions between "compressed" and "not compressed" states, based on if there's higher total population in 1 or in 2'''
        projectors = [qt.measurement.measurement_statistics(eigstates[0], num_op)[1] for num_op in self.num_ops]
        projectors_1 = [proj[1] for proj in projectors] # Projectors onto |1>
        projectors_2 = [proj[2] for proj in projectors] # Projectors onto |2>

        mask = np.zeros(len(eigstates), dtype=bool)
        for j, eigstate in enumerate(eigstates):
            mask[j] = qt.expect(sum(projectors_2), eigstate) < 0.1
        
        return mask
    
    def eigstates_partitioned(self, n=None):
        '''Return eigenstates (Qobj) of the static Hamiltonian, partitioned into "compressed" and "not compressed" states.
        Args:
            n:  if None, return all eigenstates.
                if int, return the n-particle eigenstates.
                (Eigenstates have definite particle number only under the RWA. If the RWA is not used, then particle occupations of
                eigenstates are rounded to the nearest integer.'''
        eigstates_n = self.eigstates(n)
        mask = self.partition_compressed(eigstates_n)
        return eigstates_n[mask], eigstates_n[~mask]

class M_qubit_sys_reduced(M_qubit_sys):
    def __init__(self, w, U, couplings, time_deps={}, T1s=None, T2s=None, RWA=True, N=3, reduce_Hamil_to_n=None, verbose=True):
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
        super().__init__(w, U, couplings, time_deps, T1s, T2s, RWA, N, verbose)
        self.Hamil_n = reduce_Hamil_to_n
        occupation_list = sum(self.num_ops).diag()
        self.indices_n = np.nonzero(np.isin(occupation_list, reduce_Hamil_to_n))[0]
        
        self.reduce_Hamiltonian_to_num(reduce_Hamil_to_n)
        
        # Cannot do T1 since it's not particle conserving, but can do T2
        c_ops = []
        T1s = [None]*(1+self.M)
        # Implement dephasing
        T2s = [None]*self.M if T2s is None else T2s
        T2s = np.insert(T2s, 0, None) # So we can 1-index
        for j in range(1, self.M+1):
            if T2s[j] is not None:
                gamma = 1/T2s[j] - (1/(2*T1s[j]) if T1s[j] is not None else 0) # = 1/Tphi
                c_ops.append(np.sqrt(gamma/2)*2*self.num_ops[j-1]) #sqrt(gamma/2)*sigmaz, but sigmaz = 2*n - I, and I doesn't do anything in Lindblad
            
        self.c_ops = c_ops               


    # @lru_cache
    def extract_states(self, oper):
        return qt.Qobj(oper.to("CSR").data_as("csr_matrix")[self.indices_n, :][:, self.indices_n])
    
    def reduce_ket(self, ket):
        return qt.Qobj(ket.to("CSR").data_as("csr_matrix")[self.indices_n])
    def Jhat(self, q1, q2):
            return self.extract_states(super().Jhat(q1, q2))

    # def Jcorr(self, q1_q2, q3_q4):
    #     return self.extract_states(super().Jcorr(q1_q2, q3_q4))
    
    def BOI(self):
        return self.extract_states(super().BOI())
    
    def reduce_Hamiltonian_to_num(self, n):
        '''Reduce the Hamiltonians to be limited to the particular number subspace'''
        if self.verbose:
            print(f"Reduced {self.H_static.shape[0]}^2-dimensional subspace to a {len(self.indices_n)}^2-dimensional one.")
        
        self.H_static = self.extract_states(self.H_static)
        for j in range(len(self.H_time_dep)):
            if isinstance(self.H_time_dep[j], list):
                self.H_time_dep[j][0] = self.extract_states(self.H_time_dep[j][0])
            else:
                self.H_time_dep[j] = self.extract_states(self.H_time_dep[j])
        self.num_ops = [self.extract_states(num) for num in self.num_ops]
        self.n_ops = [None]+ self.num_ops
        # self.a = {i: self.extract_states(op) for i, op in self.a.items()}
        # self.ad = {i: self.extract_states(op) for i, op in self.ad.items()}

        self.diagonalized = False

    # Print a reduced qutip vector in ket form
    def ket_form_reduced(self, state):
        pass
        # Ns, dims = state.dims
        # assert all(d==1 for d in dims), "State must be a tensor of kets"
        # comp_basis = itertools.product(*(range(N) for N in Ns))
        
        # string = ""
        # first = True
        # for ijk in comp_basis:
        #     # print(Ns, ijk)
        #     overlap = state.overlap(qt.fock(Ns, list(ijk)))
        #     mag = np.abs(overlap)
        #     angle = np.angle(overlap)

        #     ## string components
        #     coeff_mag = f"√({Fraction(mag**2).limit_denominator()})" if not np.isclose(mag,1) else ""
        #     sign = (" " if not first else "") + ("- " if angle==np.pi else "+ " if not first else "")
        #     arg = "" if angle == np.pi or angle==0 else f"exp({Fraction(angle/np.pi).limit_denominator()}πi)"
            
        #     if not np.isclose(mag,0, atol=1e-5):
        #         first = False
        #         string += (f'{sign}{coeff_mag}{arg}|{"".join(str(i) for i in ijk)}>')
        # print(string)



# Print a qutip vector in ket form
def ket_form(state):
    Ns, dims = state.dims
    assert all(d==1 for d in dims), "State must be a tensor of kets"
    comp_basis = itertools.product(*(range(N) for N in Ns))
    
    string = ""
    first = True
    for ijk in comp_basis:
        # print(Ns, ijk)
        overlap = state.overlap(qt.fock(Ns, list(ijk)))
        mag = np.abs(overlap)
        angle = np.angle(overlap)

        ## string components
        coeff_mag = f"√({Fraction(mag**2).limit_denominator()})" if not np.isclose(mag,1) else ""
        sign = (" " if not first else "") + ("- " if angle==np.pi else "+ " if not first else "")
        arg = "" if angle == np.pi or angle==0 else f"exp({Fraction(angle/np.pi).limit_denominator()}πi)"
        
        if not np.isclose(mag**2,0, atol=1e-5):
            first = False
            string += (f'{sign}{coeff_mag}{arg}|{"".join(str(i) for i in ijk)}>')
    print(string)

def step(start, end, step_time):
    return lambda t: np.heaviside(t-step_time, 0.5) * end + np.heaviside(-(t-step_time), 0.5) * start

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


### This function is too complicated, it takes 10 times as long to simulate as simple_exp_ramp
# def exp_ramp(t_pts, freq_pts, taus):
#     '''t_pts: time points
#        freq_pts: frequency at each time point
#        taus: exponential time constant of the length of each interval'''
#     t_pts = np.asarray(t_pts)
#     freq_pts = np.asarray(freq_pts)
#     taus = np.asarray(taus)
#     def ii(t):
#         return np.searchsorted(t_pts, t)

#     def func(t):
#         _ii = np.searchsorted(t_pts, t)  # interval index
#         res = np.piecewise(t, condlist=[_ii==0, _ii==len(t_pts)],
#                      funclist=[freq_pts[0], freq_pts[-1],
#                                lambda t: freq_pts[ii(t)-1] + (freq_pts[ii(t)]-freq_pts[ii(t)-1]) \
#                                * (np.exp(-(t-t_pts[ii(t)-1]) / (t_pts[ii(t)] - t_pts[ii(t)-1]) * taus[ii(t)-1]) -1) \
#                                / (np.exp(-taus[ii(t)-1]) - 1)
#                                ])
#         return res.item() if not res.shape else res
    
#     return func

def simple_exp_ramp(start, end, length, tau):
    def f(t):
        t = np.clip(t, 0, length)
        return start + (end-start) * (np.exp(-t/length*tau)-1)/(np.exp(-tau)-1)
    return f

def simple_exp_ramp_2(start, end, length, params):
    tau1, A1, tau2 = params
    def func(t):
        if t == 0:
            return start
        elif t >= length:
            return end
        else:
            return start + (end-start) * (A1*np.exp(-t/length*tau1)+(1-A1)*np.exp(-t/length*tau2)-1)\
                /(A1*np.exp(-tau1)+(1-A1)*np.exp(-tau2)-1)
    def f(t):
        try:
            return np.array([func(tt) for tt in t])
        except:
            return func(t)
    return f

# def simple_exp_ramp_3(start, end, length, params):
#     tau1, A1, tau2, A2, tau3 = params
#     def func(t):
#         if t == 0:
#             return start
#         elif t >= length:
#             return end
#         else:
#             return start + (end-start) * (A1*np.exp(-t/length*tau1)+A2*np.exp(-t/length*tau2)+(1-A1-A2)*np.exp(-t/length*tau3)-1)\
#                 /(A1*np.exp(-tau1)+A2*np.exp(-tau2)+(1-A1-A2)*np.exp(-tau3)-1)
#     def f(t):
#         try:
#             return np.array([func(tt) for tt in t])
#         except:
#             return func(t)
#     return f

def simple_exp_ramp_3(start, end, length, params):
    tau1, A1, tau2, A2, tau3 = params
    def func(t):
        return np.heaviside(t-length, 0.5) * end + \
                   np.heaviside(-(t-0), 0.5) * start + \
                   (start + (end-start) * (A1*np.exp(-t/length*tau1)+A2*np.exp(-t/length*tau2)+(1-A1-A2)*np.exp(-t/length*tau3)-1)\
                   /(A1*np.exp(-tau1)+A2*np.exp(-tau2)+(1-A1-A2)*np.exp(-tau3)-1))*np.heaviside(-(t-length), 0.5) * np.heaviside(t-0, 0.5)
    return func

def polyn_ramp(start, end, length, params):
    a, b, c = params
    def func(t):
        if t == 0:
            return start
        elif t >= length:
            return end
        else:
            return start + (end-start) * (a*(t/length)**2 + b*(t/length) + c)
    def f(t):
        try:
            return np.array([func(tt) for tt in t])
        except:
            return func(t)
    return f

def bezier_ramp(start, end, length, params):
    pass

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

def simple_ramp(fstart, fend, duration):
    return cubic_ramp([0, duration], [fstart, fend], [-1])

def double_ramp(fstart, fend, duration):
    return cubic_ramp([0, duration, 2*duration], [fstart, fend, fstart], [-1, 1])

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

