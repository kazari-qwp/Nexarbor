"""``hone``: convert CSV files into automatically nested JSON.

Only ``Hone`` is exported at package level::

    import hone
    hone.Hone is hone.hone.Hone  # True
"""

from hone.hone import Hone

__all__ = ["Hone"]
__version__ = "1.0.0"
