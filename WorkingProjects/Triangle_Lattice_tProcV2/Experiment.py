import os
import json
import numpy as np
import h5py
import datetime
from pathlib import Path

class MakeFile(h5py.File):
    def __init__(self, *args, **kwargs):
        h5py.File.__init__(self, *args, **kwargs)
        self.flush()

    def add(self, key, data):
        # print(f'Adding {key}: {data}')
        data = np.array(data)

        # print(data)
        if key in self:
            del self[key]
        try:
            self.create_dataset(key, shape=data.shape,
                            maxshape=tuple([None] * len(data.shape)),
                            dtype=str(data.astype(np.float64).dtype))
        except:
            print(f'warning: type of ({key}: {data}) is not float')
            if key in ['readout_list', 'Qubit_Readout_List']:
                data = np.array([int(qubit_str[0]) for qubit_str in data])
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))

        # if key not in self:
        #     try:
        #         self.create_dataset(key, shape=data.shape,
        #                         maxshape=tuple([None] * len(data.shape)),
        #                         dtype=str(data.astype(np.float64).dtype))
        #     except:
        #         print(f'warning: type of ({key}: {data}) is not float')
        #         if key in ['readout_list', 'Qubit_Readout_List']:
        #             data = np.array([int(qubit_str[0]) for qubit_str in data])
        #         self.create_dataset(key, shape=data.shape,
        #                             maxshape=tuple([None] * len(data.shape)),
        #                             dtype=str(data.astype(np.float64).dtype))
        # else:
        #     del self[key]
        #     self.create_dataset(key, shape=data.shape,
        #                         maxshape=tuple([None] * len(data.shape)),
        #                         dtype=str(data.astype(np.float64).dtype))
        self[key][...] = data


class NpEncoder(json.JSONEncoder):
    """ Ensure json dump can handle np arrays """
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


class ExperimentClass:
    """Base class for all experiments"""

    def __init__(self, path='', prefix='data', soc=None, soccfg=None, cfg = None, config_file=None,
                 liveplot_enabled=False, **kwargs):
        """ Initializes experiment class
            @param path - directory where data will be stored
            @param prefix - prefix to use when creating data files
            @param config_file - parameters for config file specified are loaded into the class dict
                                 (name relative to expt_directory if no leading /)
                                 Default = None looks for path/prefix.json
            @param **kwargs - by default kwargs are updated to class dict
            also loads InstrumentManager, LivePlotter, and other helpers
        """

        self.__dict__.update(kwargs)
        self.path = path
        datetimenow = datetime.datetime.now()
        datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
        datestring = datetimenow.strftime("%Y_%m_%d")
        self.prefix = prefix
        self.cfg = cfg ### .copy()
        self.soc = soc
        self.soccfg = soccfg
        if config_file is not None:
            self.config_file = os.path.join(path, config_file)
        else:
            self.config_file = None
        # self.im = InstrumentManager()
        # if liveplot_enabled:
        #     self.plotter = LivePlotClient()
        # self.dataserver= dataserver_client()

        ##### check to see if the file path exists
        DataFolderBool = Path(self.outerFolder + self.path).is_dir()
        if DataFolderBool == False:
            os.makedirs(self.outerFolder + self.path)
        DataSubFolderBool = Path(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring)).is_dir()
        if DataSubFolderBool == False:
            os.makedirs(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring))

        self.titlename = self.path + "_"+datetimestring + "_" + self.prefix
        self.fname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.h5')
        self.iname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.png')
        ### define name for the config file
        self.cname = os.path.join(self.outerFolder +  self.path, self.path + "_" + datestring, self.path + "_" + datetimestring + "_" + self.prefix + '.json')



    def save_config(self):
        if self.cname[:-3] != '.h5':
            with open(self.cname, 'w') as fid:
                json.dump(self.cfg, fid, cls=NpEncoder),
            self.datafile().attrs['config'] = json.dumps(self.cfg, cls=NpEncoder)

    def datafile(self, group=None, remote=False, data_file = None, swmr=False):
        """returns a SlabFile instance
           proxy functionality not implemented yet"""
        if data_file ==None:
            data_file = self.fname

        f = MakeFile(data_file, 'a')

        return f

    def go(self, save=False, analyze=False, display=False, progress=False):
        # get data

        data=self.acquire(progress)
        if analyze:
            data=self.analyze(data)
        if save:
            self.save_data(data)
        if display:
            self.display(data)

    def acquire(self, progress=False, debug=False):
        pass

    def analyze(self, data=None, **kwargs):
        pass

    def display(self, data=None, **kwargs):
        pass

    def save_data(self, data=None):  #do I want to try to make this a very general function to save a dictionary containing arrays and variables?
        if data is None:
            data=self.data

        with self.datafile() as f:
            for k, d in data.items():
                f.add(k, d)
                # try:
                #     print(f'd: {d}')
                #     print(type(d))
                #     _d = d
                #     while isinstance(_d, (list, tuple)):
                #         _d = _d[0]
                #         print(f'_d: {_d}')
                #         print(type(_d))
                #     if isinstance(_d, str):
                #         f.add(k, d)
                #     else:
                #         f.add(k, np.array(d))
                # except Exception as e:
                #     print('key:',k,', value:', d)
                #     raise e

    def load_data(self, f):
        data={}
        for k in f.keys():
            data[k]=np.array(f[k])
        data['attrs']=f.get_dict()
        return data

    def acquire_save(self, **kwargs):
        data = self.acquire(**kwargs)
        self.save_data(data)
        return data

    def acquire_save_display(self, **kwargs):
        data = self.acquire()
        self.save_data(data)
        self.save_config()
        self.display(data, **kwargs)
        return data

    def acquire_display_save(self, **kwargs):
        data = self.acquire()
        self.display(data, **kwargs)
        self.save_data(data)
        self.save_config()
        return data