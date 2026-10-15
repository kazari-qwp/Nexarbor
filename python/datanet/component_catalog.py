"""Standard-library component discovery and selected dependency resolution."""
import json
import os
import re
from pathlib import Path

KINDS = {'capabilities', 'nodes', 'toolboxes', 'network_presets'}


def component_root():
    return Path(os.environ.get('DATANET_COMPONENT_ROOT', Path(__file__).resolve().parents[2] / 'extensions/.none')).resolve()


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def discover(root=None):
    root = Path(root or component_root()).resolve()
    catalog, visited = {}, set()

    def visit(directory):
        directory = directory.resolve()
        if directory in visited:
            return
        visited.add(directory)
        package = read_json(directory / 'extension.json', {})
        for source in package.get('sources', []):
            target = (directory / source).resolve()
            if not target.is_dir():
                raise ValueError('Missing component source: ' + str(target))
            visit(target)
        for file in sorted(directory.glob('*/*/component.json')):
            manifest = read_json(file, {})
            key = manifest['id']
            if manifest['kind'] not in KINDS or not re.fullmatch(manifest['kind']+r'/[a-z][a-z0-9_-]*', key):
                raise ValueError('Invalid component identity: ' + key)
            if key in catalog:
                raise ValueError('Duplicate component ID: ' + key)
            value = dict(manifest, version=manifest.get('version', '0.4.0'))
            value['implementation_directory'] = file.parent
            value['package_directory'] = directory
            value['directory'] = (file.parent / value.get('resources', '.')).resolve()
            if not value['directory'].is_relative_to(directory):
                raise ValueError('Resource outside component source: ' + key)
            catalog[key] = value
    visit(root)
    return catalog


def _version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Expected numeric major.minor.patch version: ' + value)
    return tuple(map(int, value.split('.')))


def matches(version, constraint):
    actual = _version(version)
    for part in constraint.split(','):
        match = re.fullmatch(r'\s*(>=|<=|==|!=|>|<)?\s*(\d+\.\d+\.\d+)\s*', part)
        if not match:
            raise ValueError('Invalid component version constraint: ' + constraint)
        operator, expected = match.group(1) or '==', _version(match.group(2))
        if not {'>=': actual >= expected, '<=': actual <= expected, '==': actual == expected,
                '!=': actual != expected, '>': actual > expected, '<': actual < expected}[operator]:
            return False
    return True


def dependency(reference):
    return (reference, None) if isinstance(reference, str) else (reference['id'], reference.get('version'))


def resolve(root=None, selection=None, profile=None):
    root = Path(root or component_root()).resolve()
    catalog = discover(root)
    package = read_json(root / 'extension.json', {})
    if selection is None:
        configured = os.environ.get('DATANET_COMPONENT_SELECTION')
        selection = json.loads(configured) if configured else read_json(root / 'selection.json', package).get('select', [])
    flags = read_json(root / 'profile.json', {})
    flags.update(json.loads(os.environ.get('DATANET_COMPONENT_PROFILE', '{}')))
    flags.update(profile or {})
    selected = set(selection) | {key for key, value in flags.items() if value is True}
    if '*' in selected:
        selected = set(catalog)
    missing = selected - catalog.keys()
    if missing:
        raise ValueError('Unknown selected components: ' + ', '.join(sorted(missing)))
    ordered, visiting, done, blocked = [], [], set(), set()

    def visit(key):
        if key in done:
            return key not in blocked
        if key in visiting:
            raise ValueError('Component dependency cycle: ' + ' -> '.join([*visiting, key]))
        visiting.append(key)
        available = flags.get(key, True) is not False
        if not available:
            visiting.pop()
            done.add(key)
            blocked.add(key)
            return False
        for reference in catalog[key].get('requires', []):
            target, constraint = dependency(reference)
            if target not in catalog:
                raise ValueError('Missing component dependency: ' + key + ' -> ' + target)
            if constraint and not matches(catalog[target]['version'], constraint):
                raise ValueError('Component version conflict: ' + key + ' requires ' + target + ' ' + constraint)
            available = visit(target) and available
        visiting.pop()
        done.add(key)
        if available:
            ordered.append(key)
        else:
            blocked.add(key)
        return available
    for key in sorted(selected):
        visit(key)
    return catalog, ordered, blocked


def mount_paths(root=None):
    import sys
    catalog, order, _ = resolve(root)
    for key in order:
        manifest = catalog[key]
        if manifest.get('python', {}).get('path'):
            directory = (manifest['implementation_directory'] / manifest['python']['path']).resolve()
            if not directory.is_relative_to(manifest['implementation_directory']):
                raise ValueError('Python implementation outside component: ' + key)
            if str(directory) not in sys.path:
                sys.path.append(str(directory))
    return catalog, order


def tool_bindings(catalog, order):
    result = {}
    for key in order:
        manifest = catalog[key]
        if manifest.get('toolBindings'):
            file = (manifest['directory'] / manifest['toolBindings']).resolve()
            if not file.is_relative_to(manifest['directory']):
                raise ValueError('Tool bindings outside component: ' + key)
            for name, binding in read_json(file, {}).items():
                if name in result and result[name] != binding:
                    raise ValueError('Conflicting tool binding: ' + name)
                result[name] = binding
    return result
