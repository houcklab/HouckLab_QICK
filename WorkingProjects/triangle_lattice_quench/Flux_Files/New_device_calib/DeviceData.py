import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List
import numpy as np
import dacite
from scipy.optimize import root_scalar

# --- STORAGE CLASSES ---

@dataclass
class TransmonData:
    name: str
    role: str # 'Qubit' or 'Coupler'
    w_max: float
    w_min: float
    c: float
    ffgain_quantum: float = 0 # How much FF gain = 1.0 flux; 0 for items with no fast-flux line
    Ec: float = 180
    crosstalk_map: Dict[str, float] = field(default_factory=dict) # {FluxLineID: Sensitivity}
    

    def freq(self, flux:float):
        '''converts a value of flux (dimensionless) to frequency'''
        A = self.w_max + self.c
        B = self.w_min + self.c
        return np.sqrt(A**2 * np.cos(np.pi*flux)**2 + B**2 * np.sin(np.pi*flux)**2) - self.c

    def flux(self, freq):
        '''converts a value of frequency to flux (dimensionless).'''
        
        bracket = (-0.5, 0)
        if isinstance(freq, (list, np.ndarray)):
            fluxes = np.empty(len(freq))
            for i in range(len(freq)):
                root_function = lambda flux: self.freq(flux) - freq[i]
                result = root_scalar(root_function, bracket=bracket)
                fluxes[i] = result.root
            return fluxes
        elif isinstance(freq, (int, float)):
            if freq < self.w_min:
                raise ValueError(f"Frequency of {self.name} is below minimum {self.w_min}")
                print(f"Frequency of {self.name} set to minimum {self.w_min}")
                return 0.5
            elif freq > self.w_max:
                raise ValueError(f"Frequency of {self.name} is above maximum {self.w_max}")
                print(f"Frequency of {self.name} set to maximum {self.w_max}")
                return 0
            root_function = lambda flux: self.freq(flux) - freq
            result = root_scalar(root_function, bracket=bracket)
            return result.root

@dataclass
class Coupling:
    ''''''
    q1: str
    q2: str
    gamma: float # where J = gamma/4000 * np.sqrt((w1+Ec)(w2+Ec)), gamma ~ coupling at 4 GHz

@dataclass
class DeviceData:
    name: str
    timestamp: str
    transmons: Dict[str, TransmonData] = field(default_factory=dict)
    couplings: List[Coupling] = field(default_factory=list)
    zero_voltage_fluxes: Dict[str, float] = field(default_factory=dict) # drifts over time / between cooldowns

    def to_json(self, path: str | None = None, indent: int = 2) -> str:
        text = json.dumps(asdict(self), indent=indent)
        if path is not None:
            with open(path, "w") as f:
                f.write(text)
        return text

    @classmethod
    def from_json(cls, source: str) -> "DeviceData":
        # `source` may be a JSON string or a path to a JSON file.
        try:
            data = json.loads(source)
        except json.JSONDecodeError:
            with open(source) as f:
                data = json.load(f)
        return dacite.from_dict(data_class=cls, data=data)