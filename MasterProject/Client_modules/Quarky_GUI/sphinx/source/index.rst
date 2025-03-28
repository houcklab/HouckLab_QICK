The Quantum Quarky
==================

Welcome to the Quarky documentation, the home of the graphical
user interface for all quantum experiments using RFSoCs.

Supports MacOS and Windows.

******************

Getting Started
^^^^^^^^^^^^^^^

.. _getting_started:

This section will guide you through setting up and using the Quarky GUI for the first time, writing your own
experiments, and understanding the fundamental features of the interface.


Running the GUI for the First Time
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To run the Quarky GUI for the first time, follow these steps:

    1. **Pulling from Git:**

       Ensure you have the latest version of Quarky by cloning or pulling from the `Link HouckLab_QICK repository <https://github.com/houcklab/HouckLab_QICK>`_.
       Currently, the GUI resides on the ``quarky-development`` branch.

    2. **Configuring Environment:**

       Set up the required dependencies and environment variables for Quarky. All required packages are given in the ``requirements.txt`` file found in the ``Quarky_GUI`` folder.
       To use the file, ensure you are in the correct directory in command line and use the following commands as appropriate:

       ::

        # To update existing quarky_env conda environment
        conda activate your_env_name
        pip install -r requirements.txt

        # To create a quarky_env conda environment from scratch if one does not exist
        conda create --name your_env_name
        conda activate your_env_name
        pip install -r requirements.txt

    3. **Executing GUI**
       Launch the GUI after environment activation via ``python Quarky.py`` on the command line and verify that it runs correctly.


GUI Basics
~~~~~~~~~~
See the Quarky GUI section for GUI basics and documentation.

Writing an Experiment
~~~~~~~~~~~~~~~~~~~~~
See the Experiment Hub for how to write/edit your own experiment.


******************


Explore Documentation
^^^^^^^^^^^^^^^^^^^^^

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   experiment_class
   quarky_modules