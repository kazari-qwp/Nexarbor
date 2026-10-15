"""Use extended Windows paths for graph storage without changing machine settings."""
import os
from pathlib import Path


def storage_path(value):
    absolute = os.path.abspath(value)
    if os.name == 'nt' and not absolute.startswith('\\\\?\\'):
        absolute = ('\\\\?\\UNC\\' + absolute[2:] if absolute.startswith('\\\\')
                    else '\\\\?\\' + absolute)
    return Path(absolute).resolve()
