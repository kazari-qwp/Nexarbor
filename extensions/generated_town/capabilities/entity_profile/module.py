"""Generic entity record: profile fields, coin balance and item counts.

Each mounted node owns one JSON state. Other components read and change it only
through trusted operations; the single Agent-facing tool is read-only, so no
tool lets an Agent rewrite its own belongings. Profile values are published
through the core metadata registry, balances never go negative, and every
change is computed completely before it is committed.
"""
from copy import deepcopy

from datanet.core.json_values import freeze, thaw
from datanet.studio.contract import StudioModule

METADATA_NAMESPACE = 'profile'


def _plain(value, label):
    """Return a detached JSON-safe copy or raise a plain ValueError."""
    try:
        return thaw(freeze(value))
    except ValueError as error:
        raise ValueError(label + ' must contain finite JSON values with string keys') from error


def _count(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(label + ' must be an integer of at least ' + str(minimum))
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Item names must be nonempty strings')
    return value


def _quantities(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + ' must be an object of item counts')
    result = {}
    for name, quantity in value.items():
        key = _name(name)
        result[key] = _count(quantity, 'Quantity of ' + key)
    return result


def _deltas(value):
    if not isinstance(value, dict):
        raise ValueError('Item changes must be an object of integer deltas')
    result = {}
    for name, delta in value.items():
        key = _name(name)
        if type(delta) is not int:
            raise ValueError('Delta of ' + key + ' must be an integer')
        result[key] = delta
    return result


class Module(StudioModule):
    def setup(self):
        profile = _plain(self.config.get('profile', {}), 'Initial profile')
        if not isinstance(profile, dict):
            raise ValueError('Initial profile must be an object')
        self.state.setdefault('profile', profile)
        self.state.setdefault('coins', _count(self.config.get('coins', 0), 'Initial coins'))
        self.state.setdefault('items', _quantities(self.config.get('items', {}), 'Initial items'))
        namespace = self.config.get('metadata_namespace', METADATA_NAMESPACE)
        if not isinstance(namespace, str) or not namespace.strip() or namespace == 'core':
            raise ValueError('metadata_namespace must be one nonempty name other than core')
        self.namespace = namespace
        self._metadata_owner = self.manifest['id'] + '/' + self.node.node_id
        self._metadata_registry = None
        self._publish_metadata()

    # The core metadata registry stays the single read path; this component only
    # contributes one namespaced entry and removes it again when it is unused.
    def _publish_metadata(self):
        registry = getattr(self.backend, 'metadata_registry', None)
        if registry is None:
            registry = getattr(self.node, '_metadata_registry', None)
        if registry is None or not hasattr(registry, 'register'):
            return

        def provider(target):
            return self._metadata_fields(target)

        registry.register(self._metadata_owner, provider)
        self._metadata_registry = registry

    def _metadata_fields(self, target):
        if target != self.node.node_id or not self.active:
            return {}
        fields = _plain(dict(self.state['profile']), 'Profile')
        return {self.namespace: fields} if fields else {}

    def close(self):
        super().close()
        registry = getattr(self, '_metadata_registry', None)
        if registry is not None and hasattr(registry, 'unregister'):
            registry.unregister(self._metadata_owner)
            self._metadata_registry = None

    def snapshot(self):
        return dict(profile=deepcopy(self.state['profile']), coins=self.state['coins'], items=dict(self.state['items']))

    def read(self):
        return self.snapshot()

    def update_profile(self, fields):
        values = _plain(fields, 'Profile fields')
        if not isinstance(values, dict):
            raise ValueError('Profile fields must be an object')
        profile = dict(self.state['profile'])
        profile.update(values)
        self.state['profile'] = profile
        return self.snapshot()

    def adjust(self, coins=None, items=None, fields=None):
        balance = self.state['coins']
        profile = self.state['profile']
        stock = dict(self.state['items'])
        if coins is not None:
            if type(coins) is not int:
                raise ValueError('Coin delta must be an integer')
            balance = balance + coins
        if items is not None:
            for name, delta in _deltas(items).items():
                stock[name] = stock.get(name, 0) + delta
        if fields is not None:
            values = _plain(fields, 'Profile fields')
            if not isinstance(values, dict):
                raise ValueError('Profile fields must be an object')
            profile = dict(profile)
            profile.update(values)
        # Every value is checked before the first write, so a failure leaves the
        # whole record untouched instead of applying half of the request.
        if balance < 0:
            raise ValueError('Coin balance cannot be negative')
        for name, quantity in stock.items():
            if quantity < 0:
                raise ValueError('Quantity of ' + name + ' cannot be negative')
        self.state['coins'] = balance
        self.state['profile'] = profile
        self.state['items'] = {name: quantity for name, quantity in stock.items() if quantity > 0}
        return self.snapshot()

    def entity_view(self):
        return self.snapshot()
