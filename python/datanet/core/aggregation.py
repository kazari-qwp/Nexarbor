"""Order-independent merging of one breadth-first layer's incoming strengths.

Node.aggregation is sum (default), max, min or mean. Both graph access and
signal delivery use it after edge filtering/multipliers, before adding the
receiving node's divergence. Only actual inputs contribute to the mean;
one merged delivery still activates the receiver once. Each traversal keeps
its own mode snapshot. Separate waves and layers are never combined.
"""
from math import fsum
from .interface import validate_strength

MODES = ('sum', 'max', 'min', 'mean')


def validate_aggregation(value):
    if not isinstance(value, str) or value not in MODES:
        raise ValueError('aggregation must be sum, max, min or mean')
    return value


def aggregate(values, mode='sum'):
    validate_aggregation(mode)
    values = tuple(validate_strength(value) for value in values)
    if not values:
        raise ValueError('Cannot aggregate an empty set of inputs')
    try:
        if mode == 'max': result = max(values)
        elif mode == 'min': result = min(values)
        elif mode == 'mean':
            scale = max(values)
            result = scale * (fsum(value / scale for value in values) / len(values)) if scale else 0
        else: result = sum(values) if all(type(v) is int for v in values) else fsum(values)
    except OverflowError as error:
        raise ValueError('Aggregated strength must be finite') from error
    return validate_strength(result)
