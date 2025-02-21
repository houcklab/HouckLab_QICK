import os
import importlib
import h5py

def import_file(full_path_to_module):
    """
     Function used to import experiment files as module.
    :param full_path_to_module: string
    :return: module_obj: the object representing the imported module
     module_name: the name of the imported module
    """
    try:
        module_dir, module_file = os.path.split(full_path_to_module)
        module_name, module_ext = os.path.splitext(module_file)
        loader = importlib.machinery.SourceFileLoader(module_name, full_path_to_module)
        module_obj = loader.load_module()
        module_obj.__file__ = full_path_to_module
        globals()[module_name] = module_obj
    except Exception as e:
        raise ImportError(e)
    return module_obj, module_name

def h5_to_dict(h5file):
    with h5py.File(h5file, "r") as f:
        data_dict = {}
        for key in f.keys():
            data_dict[key] = f[key][()]  # Load dataset into memory
        return data_dict