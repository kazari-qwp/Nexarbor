"""Adapter for pinned llm-wiki algorithms; no LLM, shell, network or vault mutation."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import yaml


def labels(value):
    # YAML plain scalars can become numbers, booleans or dates. The upstream
    # page contract expects string labels; never forward parser-specific types.
    values=value if isinstance(value,list) else [] if value is None else [value]
    if any(isinstance(item,(dict,list,set)) for item in values):
        raise ValueError('Wiki aliases and tags must be scalar labels')
    return list(dict.fromkeys(str(item) for item in values if item is not None))


def page(record):
    content = record['content']
    metadata = dict(record.get('metadata', {}))
    if content.startswith('---\n'):
        parts = content.split('\n---', 1)
        if len(parts) == 2:
            fields = yaml.safe_load(parts[0][4:]) or {}
            if isinstance(fields, dict):metadata.update(fields)
            content = parts[1].lstrip('\r\n')
    return dict(slug=record['id'], title=str(metadata.get('title', record['key'])),
                aliases=list(dict.fromkeys([str(record['key']), *labels(metadata.get('aliases'))])),
                tags=labels(metadata.get('tags')), description=str(metadata.get('description', '')),
                content=content, wikilinks=list(dict.fromkeys(link.strip() for link in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content))))


def run(directory, operation, records, *, query='', limit=10, node_binary=None):
    binary = node_binary or shutil.which('node')
    if not binary:
        raise RuntimeError('llm-wiki requires Node.js 22.18+ (native TypeScript support)')
    result = subprocess.run([str(binary), str(Path(directory) / 'bridge.mjs')],
        input=json.dumps(dict(operation=operation, pages=[page(r) for r in records], query=query, limit=limit), ensure_ascii=False),
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('llm-wiki execution failed: ' + result.stderr[-1500:])
    return json.loads(result.stdout)
