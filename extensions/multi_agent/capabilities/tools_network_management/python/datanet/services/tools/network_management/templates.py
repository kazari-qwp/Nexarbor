"""Expand repeatable member templates before mounting an ordinary network package."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json
from datanet.core.component_registry import codecs


def expand_package(source, arguments, directory, specification):
    source = Path(source)
    document = json.loads(source.read_text(encoding='utf-8'))
    parameter = specification['parameter']
    count = arguments.get(parameter, specification['default'])
    if type(count) is not int or not specification['minimum'] <= count <= specification['maximum']:
        raise ValueError(f"{parameter} 须为 {specification['minimum']} 至 {specification['maximum']} 的整数")
    template_id = specification['node']
    ids = [specification['prefix'] + str(i + 1) for i in range(count)]

    def replace(value, target):
        if isinstance(value, str):
            return value.replace(template_id, target)
        if isinstance(value, list):
            return [replace(v, target) for v in value]
        if isinstance(value, dict):
            return {k: replace(v, target) for k, v in value.items()}
        return value

    def expand(value):
        if isinstance(value, list):
            result = []
            for item in value:
                repeated = item == template_id if isinstance(item, str) else isinstance(item, dict) and any(item.get(k) == template_id for k in ('target_node_id', 'target', 'source'))
                result.extend([replace(item, id) for id in ids] if repeated else [expand(item)])
            return result
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value

    nodes = []
    for entry in document['network']['nodes']:
        if entry['node_id'] == template_id:
            nodes.extend(replace(deepcopy(entry), id) for id in ids)
        else:
            nodes.append(expand(entry))
    document['network']['nodes'] = nodes
    document['network']['delegations'] = expand(document['network']['delegations'])
    # Preserve source-relative resources when the expanded package is saved elsewhere.
    for entry in nodes:
        for label in codecs()[entry['type']].resources:
            if label in entry['parameters']:
                entry['parameters'][label] = str((source.parent / entry['parameters'][label]).resolve())
        if entry.get('agent'):
            entry['agent']['package'] = str((source.parent / entry['agent']['package']).resolve())
    folder = Path(directory) / 'expanded-presets' / uuid4().hex
    folder.mkdir(parents=True)
    path = folder / 'package.json'
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, count
