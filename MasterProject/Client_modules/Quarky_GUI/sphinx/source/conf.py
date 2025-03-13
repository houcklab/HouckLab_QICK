# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
sys.path.insert(0, os.path.abspath("../../"))
print(sys.path)

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Quarky'
copyright = '2025, Lev, Jake, Matt, Sonny'
author = 'Lev, Jake, Matt, Sonny'
release = '1.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autodoc"]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'sphinx_book_theme'
html_theme = 'furo'
# html_theme = 'pydata_sphinx_theme'

# Theme options (customize appearance)
html_theme_options = {
    "github_url": "https://github.com/houcklab/HouckLab_QICK/tree/quarky-development/MasterProject/Client_modules/Quarky_GUI",
    "secondary_sidebar_items": ["page-toc"],
}

html_static_path = ['_static']
