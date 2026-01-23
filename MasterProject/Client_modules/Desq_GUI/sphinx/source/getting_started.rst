Getting Started
---------------

.. _getting_started:

This section will guide you through setting up and using Desq for the first time.


Running Desq for the First Time
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To run the Desq GUI for the first time, follow these steps:

    1. **Pulling from Git:**

       Ensure you have the latest version of Desq by cloning or pulling from the `HouckLab_QICK repository <https://github.com/houcklab/HouckLab_QICK>`_.
       Currently, the GUI resides on the ``desq_dev`` branch `here <https://github.com/houcklab/HouckLab_QICK/tree/desq_dev/MasterProject/Client_modules/Desq_GUI>`_.

    2. **Configuring Environment:**

       Set up the required dependencies and environment variables for Desq. All required packages are given in the ``requirements.txt`` file found in the ``Desq_GUI`` folder.
       To use the file, ensure you are in the correct directory in command line and use the following commands as appropriate:

       ::

        # To update existing Desq_env conda environment
        conda activate your_env_name
        pip install -r requirements.txt

        # To create a Desq_env conda environment from scratch if one does not exist
        conda create --name your_env_name
        conda activate your_env_name
        pip install -r requirements.txt


       If any packages are rejected or errors arise, resolve each package independently after you activate your environment via ``pip`` installations.
       Most installation issues can typically be resolved by searching for the specific error online.

    3. **Executing Desq**
       Launch Desq after environment activation by navigating to root ``HouckLab_QICK`` directory and running the command ``python -m MasterProject.Client_modules.Desq_GUI.Desq`` on the terminal and verify that it runs correctly.

       .. note::
            Setting up a running configuration can also be helpful (such as on PyCharm). Ensure the environment is set, the script is ``Desq.py``, and the working directory is the direct path to (and including) ``HouckLab_QICK``.

