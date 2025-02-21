import os
import importlib

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