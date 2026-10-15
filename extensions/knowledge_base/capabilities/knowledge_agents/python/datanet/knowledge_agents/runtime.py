"""One main knowledge Agent with direct IO and optional, scoped task helpers."""
import csv
import json
import re
from pathlib import Path

from datanet.core.application import Component
from datanet.knowledge.services import access, connect_workers


class Plugin(Component):
    def install(self):
        self.r.backend.knowledge.embedding_config = self.r.config.get('knowledgeEmbedding')
        self.on('session/root', self.root_session)
        self.on('tool/before', self.guide)
        self.on('tool/definition', self.definition)
        self.on('tool/available', self.available)
        self.on('tool/after', self.stored)
        self.on('worker/scoped', self.scoped)
        self.on('document/validate-source', self.validate_source)
        self.on('document/validate-receipts', self.validate_receipts)

    @property
    def docs(self):
        return self.r.plugins['capabilities/task_documents']

    def guide(self, event):
        if event['name'] in {'kb_ingest', 'kb_task'} or (event['name'] == 'datanet_spawn_helper' and self.r.config.get('rootNetwork') == 'knowledge_base'):
            self.r.load(event['actor'], 'knowledge:entry', self.r.resource(self.id, 'USAGE.md'))
        if event['name'] == 'datanet_spawn_helper' and event['actor'] == 'root' and self.r.config.get('rootNetwork') == 'knowledge_base':
            self.worker_policy()

    def definition(self, event):
        if event['name'] == 'kb_create_node':
            grant = access(self.r.backend, event['actor'])
            event['spec']['parameters']['properties']['storage']['enum'] = grant['write']

    def available(self, event):
        if event['name'] in {'kb_create_node', 'kb_store', 'kb_update', 'kb_delete', 'kb_index'}:
            if not access(self.r.backend, event['actor'])['write']:
                event['allowed'] = False

    def remember_receipts(self, actor, result):
        task = self.docs.task(actor)
        records = result.get('records', [result] if 'id' in result and 'version' in result else [])
        ledger = task.setdefault('receipts', [])
        for record in records:
            key = dict(id=record['id'], version=record['version'])
            if key not in ledger:ledger.append(key)

    def stored(self, event):
        if event['name'] in {'kb_store', 'kb_update'} and self.r.backend.agents.get(event['actor'], {}).get('document_task'):
            self.remember_receipts(event['actor'], event['result'])
            self.r.rpc('save')

    def root_session(self, event):
        if self.r.config.get('rootNetwork') != 'knowledge_base':
            return
        self.r.rpc('knowledge_init')
        self.r.rpc('bind_agent', target='root', session_id=event['session_id'], kind='root', manager_id=None, creator_node_id=None)
        owner = 'network_presets/knowledge_base'
        event['view'] = self.r.bind('root', event['session_id'], 'knowledge_main',
            self.r.resolve(self.r.config.get('rootToolboxes', ['knowledge_base'])), self.r.resource(owner, 'prompt.md'))
        self.worker_policy()
        self.r.refresh('root')
        self.r.rpc('save')

    def worker_policy(self):
        policy = self.r.resource('network_presets/knowledge_base', 'topology.json', json_data=True)['helpers']
        policy['prompt'] = self.r.resource('nodes/knowledge_worker', 'prompt.md')
        task_id = self.r.backend.agents['root'].get('document_task')
        task = self.docs.tasks.get(task_id)
        if task and task['mode'] == 'read':
            policy['toolboxes'] = policy['readToolboxes']
            policy['scope']['storage_types'] = []
            for component in policy['components'].values():
                component['scope']['storage_types'] = []
        self.r.plugins['capabilities/scoped_workers'].register('root', policy)

    def scoped(self, event):
        # Only helpers created under this knowledge entry receive these grants.
        if event['parent'] != 'root' or self.r.config.get('rootNetwork') != 'knowledge_base':
            return
        parent = access(self.r.backend, event['parent'])
        writes = event['scope'].get('storage_types', [])
        if not set(writes).issubset(parent['write']):
            raise PermissionError('Helper storage scope exceeds parent')
        self.r.backend.agents[event['actor']]['knowledge_access'] = dict(read=parent['read'], write=writes)
        connect_workers(self.r.backend)

    def validate_source(self, event):
        if self.r.config.get('rootNetwork') != 'knowledge_base':return
        source = event['source']
        if not source['node_id'].startswith('knowledge/data/'):
            return
        if not source.get('locator') or not source.get('version'):
            raise ValueError('Knowledge evidence requires record ID (locator) and version')
        if not re.fullmatch(r'[0-9a-f]{32}', source['locator']):
            raise ValueError('Knowledge evidence locator must be one exact record ID from kb_fetch or kb_store; put explanations in content')
        record = self.r.rpc('knowledge_fetch', actor=event['actor'], id=source['locator'], version=source['version'])
        if record['node_id'] != source['node_id']:
            raise ValueError('Evidence record does not belong to this node')

    def validate_receipts(self, event):
        if self.r.config.get('rootNetwork') != 'knowledge_base':return
        for receipt in event['receipts']:
            if not receipt.get('id') or not receipt.get('version'):
                raise ValueError('A storage receipt needs an actual record ID and version')
            if dict(id=receipt['id'], version=receipt['version']) not in event['task'].get('receipts', []):
                raise ValueError('Receipt was not produced by this task')
            record = self.r.rpc('knowledge_fetch', actor=event['actor'], id=receipt['id'], version=receipt['version'])
            if receipt.get('node_id', record['node_id']) != record['node_id']:
                raise ValueError('Receipt node does not match its record')

    def tool_kb_task(self, actor, args):
        if actor != 'root':
            raise PermissionError('Only the main Agent may admit tasks')
        if args.get('mode', 'agent') == 'write':
            self.docs.begin(actor, args['content'], mode='write')
            return self.tool_kb_ingest(actor, dict(content=args['content']))
        result = self.docs.begin(actor, args['content'], mode=args.get('mode', 'agent'))
        self.r.refresh(actor)
        return result

    def tool_kb_ingest(self, actor, args):
        if actor != 'root':
            raise PermissionError('Only the main Agent may admit original materials')
        if args.get('intake_id'):
            intake = self.r.rpc('knowledge_intake', actor=actor, id=args['intake_id'])
        else:
            content = args.get('content'); source = None
            if args.get('file_path'):
                workspace = Path(self.r.config.get('workspace', self.r.directory)).resolve()
                source = Path(args['file_path'])
                source = (source if source.is_absolute() else workspace / source).resolve()
                if not source.is_relative_to(workspace):
                    raise PermissionError('Import file must be inside the application workspace')
                if source.suffix.lower() == '.csv':
                    with source.open(encoding='utf-8-sig', newline='') as f:content = list(csv.DictReader(f))
                elif source.suffix.lower() == '.json':content = json.loads(source.read_text(encoding='utf-8'))
                elif source.suffix.lower() in {'.txt', '.md'}:content = source.read_text(encoding='utf-8')
                else:raise ValueError('Supported import files: CSV, JSON, TXT, Markdown')
            if content is None:
                raise ValueError('Provide content, file_path or an existing intake_id')
            intake = self.r.rpc('knowledge_stage', actor=actor, content=content, purpose=args.get('purpose', ''), original_file=str(source) if source else None)
        # The input is immutable; large source content stays in paged intake storage.
        current = self.docs.tasks.get(self.r.backend.agents[actor].get('document_task'))
        if current and current['mode'] != 'read':
            if intake['id'] not in current['references']:
                current['references'].append(intake['id'])
            reference = self.docs.reference(actor, current)
            self.r.rpc('save')
        else:
            reference = self.docs.begin(actor, dict(intake_id=intake['id'], purpose=intake['purpose']), mode='write', references=[intake['id']])
        self.r.refresh(actor)
        target = args.get('collection') or self.r.rpc('knowledge_route', actor=actor, id=intake['id'])['collection']
        if intake['status'] == 'completed':
            result = intake['result']
        elif target:
            result = self.r.rpc('knowledge_commit_intake', actor=actor, id=intake['id'], collection=target)
        else:
            return dict(status='pending', intake_id=intake['id'], **reference)
        records = result.get('records', [])
        self.remember_receipts(actor, result)
        self.docs.tool_task_document_write(actor, dict(content=json.dumps(result, ensure_ascii=False), receipts=records))
        return dict(**result, **reference)
