###########################################################################
#############################  gui_helper.py  #############################
###########################################################################
"""
File with helper functions for LAKE_GUI
"""

import importlib
import os

def dict_override(dict1, dict2):
    ### overrides elements in dict2 with elements from dict1 that overlap
    keys = list(dict2.keys())
    num_elements = len(keys)
    new_dict = {}
    for idx in range(num_elements):
        ### attempt to override the key
        try:
            new_dict[keys[idx]] = dict1[keys[idx]]
        except:
            new_dict[keys[idx]] = dict2[keys[idx]]
    return new_dict

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