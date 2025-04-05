import os
import sys
sys.path.insert(0, os.path.abspath('..'))

project = 'DataNewsHub'
copyright = '2025, Saruman'
author = 'Saruman'
release = '1.0'

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']

templates_path = ['_templates']
exclude_patterns = []

autodoc_member_order = 'bysource'
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
