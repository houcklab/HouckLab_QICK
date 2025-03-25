import os
import json
import numpy as np
import h5py
import datetime
from pathlib import Path

class MakeFile(h5py.File):
    def __init__(self, *args, **kwargs):
        h5py.File.__init__(self, *args, **kwargs)
        # self.attrs["_script"] = open(sys.argv[0], 'r').read()
        # if self.mode is not 'r':
        # self.attrs["_script"] = get_script()
        # if not read-only or existing then save the script into the .h5
        # Maybe should take this automatic feature out and just do it when you want to
        # Automatic feature taken out. Caused more trouble than convenience. Ge Yang
        # if 'save_script' in kwargs:
        # save_script = kwargs['save_script']
        # else:
        # save_script = True
        # if (self.mode is not 'r') and ("_script" not in self.attrs) and (save_script):
        # self.save_script()
        self.flush()

    def add(self, key, data):
        data = np.array(data)
        try:
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
        except RuntimeError:
            del self[key]
            self.create_dataset(key, shape=data.shape,
                                maxshape=tuple([None] * len(data.shape)),
                                dtype=str(data.astype(np.float64).dtype))
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

    def __init__(self, path='', outerFolder='',
                    prefix='data', soc=None, soccfg=None, cfg = None, config_file=None,
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
        self.outerFolder = outerFolder
        datetimenow = datetime.datetime.now()
        datetimestring = datetimenow.strftime("%Y_%m_%d_%H_%M_%S")
        datestring = datetimenow.strftime("%Y_%m_%d")
        self.prefix = prefix
        self.cfg = cfg
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
            os.mkdir(self.outerFolder + self.path)
        DataSubFolderBool = Path(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring)).is_dir()
        if DataSubFolderBool == False:
            os.mkdir(os.path.join(self.outerFolder + self.path, self.path + "_" + datestring))

        self.fname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.h5')
        self.iname = os.path.join(self.outerFolder + self.path, self.path + "_" + datestring, self.path + "_"+datetimestring + "_" + self.prefix + '.png')
        ### define name for the config file
        self.cname = os.path.join(self.outerFolder +  self.path, self.path + "_" + datestring, self.path + "_" + datetimestring + "_" + self.prefix + '.json')
        # print(self.fname)
        #self.load_config()
    #
    # def load_config(self):
    #     if self.config_file is None:
    #         self.config_file = os.path.join(self.path, self.prefix + ".json")
    #     try:
    #         if self.config_file[-3:] == '.h5':
    #             with SlabFile(self.config_file) as f:
    #                 self.cfg = AttrDict(f.load_config())
    #                 self.fname = self.config_file
    #         elif self.config_file[-4:].lower() =='.yml':
    #             with open(self.config_file,'r') as fid:
    #                 self.cfg = AttrDict(yaml.safe_load(fid))
    #         else:
    #             with open(self.config_file, 'r') as fid:
    #                 cfg_str = fid.read()
    #                 self.cfg = AttrDict(json.loads(cfg_str))
    #
    #         if self.cfg is not None:
    #             for alias, inst in self.cfg['aliases'].items():
    #                 if inst in self.im:
    #                     setattr(self, alias, self.im[inst])
    #     except Exception as e:
    #         print("Could not load config.")
    #         traceback.print_exc()

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
        #     if swmr==True:
    #         f = SlabFile(data_file, 'w', libver='latest')
    #     elif swmr==False:
    #         f = SlabFile(data_file, 'a')
    #     else:
    #         raise Exception('ERROR: swmr must be type boolean')
    #
    #     if group is not None:
    #         f = f.require_group(group)
    #     if 'config' not in f.attrs:
    #         try:
    #             f.attrs['config'] = json.dumps(self.cfg, cls=NpEncoder)
    #         except TypeError as err:
    #             print(('Error in saving cfg into datafile (experiment.py):', err))
    #
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

    @classmethod
    def plotter(cls, plot_widget, plots, data):
        pass

    def save_data(self, data=None):  #do I want to try to make this a very general function to save a dictionary containing arrays and variables?
        if data is None:
            data=self.data

        with self.datafile() as f:
            for k, d in data.items():
                f.add(k, np.array(d))

    def load_data(self, f):
        data={}
        for k in f.keys():
            data[k]=np.array(f[k])
        data['attrs']=f.get_dict()
        return data