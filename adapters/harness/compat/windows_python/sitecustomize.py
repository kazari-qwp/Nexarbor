"""Python startup bridge for Harness's Windows write-restricted processes."""
# Preserve a user's existing startup customization before applying our bridge.
import os as _os, sys as _sys
from importlib.machinery import PathFinder as _PathFinder
from importlib.util import module_from_spec as _module_from_spec
_own = _os.path.normcase(_os.path.abspath(_os.path.dirname(__file__)))
_paths = [p for p in _sys.path if _os.path.normcase(_os.path.abspath(p)) != _own]
_spec = _PathFinder.find_spec('sitecustomize', _paths)
if _spec and _spec.loader:
    _previous = _module_from_spec(_spec)
    _spec.loader.exec_module(_previous)
from _datanet_private_dirs import install as _install
_install()
