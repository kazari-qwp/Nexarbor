"""Copy only JSON-shaped values across the module capability boundary."""
from dataclasses import asdict,is_dataclass
from .json_values import freeze,thaw

def json_copy(value):
    return thaw(freeze(asdict(value) if is_dataclass(value) else value))
