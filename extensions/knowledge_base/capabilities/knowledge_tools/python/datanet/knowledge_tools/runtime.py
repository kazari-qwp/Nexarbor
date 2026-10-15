"""Small knowledge tools over component-owned persistent services."""
from datanet.core.application import Component

OPERATIONS = {'kb_catalog':'catalog','kb_create_node':'create_collection','kb_fetch':'fetch',
              'kb_search':'search','kb_update':'update','kb_delete':'delete','kb_export':'export',
              'kb_intake':'intake','kb_index':'index','kb_query':'query'}


class Plugin(Component):
    def install(self):
        self.on('tool/before', self.guide)

    def guide(self, event):
        if event['name'].startswith('kb_'):
            file='AGENTS.md' if 'kb_store' in self.r.state(event['actor'])['grant']['framework'] else 'READING.md'
            self.r.load(event['actor'],'knowledge:archive' if file=='AGENTS.md' else 'knowledge:read',self.r.resource(self.id,file))

    def invoke(self, actor, name, arguments):
        if name == 'kb_wiki':
            return self.wiki(actor, arguments)
        if name=='kb_store':
            if arguments.get('intake_id'):
                return self.r.rpc('knowledge_commit_intake',actor=actor,id=arguments['intake_id'],collection=arguments['collection'],indices=arguments.get('indices'))
            values=dict(arguments)
            values.pop('intake_id',None)
            values['value']=values.pop('content')
            return self.r.rpc('knowledge_store',actor=actor,**values)
        if name=='kb_intake':arguments={**arguments,'preview':True}
        result=self.r.rpc('knowledge_'+OPERATIONS[name],actor=actor,**arguments)
        if name=='kb_export' and 'content' in result:
            from uuid import uuid4
            path=self.r.backend.knowledge.directory/'exports'/(uuid4().hex+'.'+result['format'])
            self.r.backend.knowledge._atomic(path,result['content'].encode('utf-8'))
            return dict(format=result['format'],count=result['count'],path=str(path))
        return result

    def wiki(self, actor, args):
        action = args.get('action', 'guide')
        workflow = args.get('workflow', 'query' if action == 'search' else 'lint' if action == 'lint' else 'ingest')
        if workflow not in ('ingest', 'query', 'lint'):
            raise ValueError('Choose ingest, query or lint')
        owner = 'capabilities/llm_wiki'
        self.r.load(actor, 'wiki:mapping', self.r.resource(self.id, 'WIKI.md'))
        added = self.r.load(actor, 'wiki:upstream:' + workflow, self.r.resource(owner, 'vendor/skills/' + workflow + '/SKILL.md'))
        if action == 'guide':return dict(instructions_added=added, engine='llm-wiki', workflow=workflow)
        if action not in ('lint', 'search'):raise ValueError('Choose guide, search or lint')
        collection = self.r.rpc('knowledge_collection', actor=actor, target=args['collection'])
        if collection['storage'] != 'wiki':raise ValueError('Choose a Wiki collection')
        records, offset = [], 0
        while True:
            hits = self.r.rpc('knowledge_search', actor=actor, collection=collection['id'], limit=1000, offset=offset)
            for hit in hits['items']:
                records.append(self.r.rpc('knowledge_fetch', actor=actor, id=hit['id']))
            if hits['next_offset'] is None:break
            offset = hits['next_offset']
        from datanet.llm_wiki.upstream import run
        result = run(self.r.catalog[owner]['directory'], action, records, query=args.get('query', ''),
                     limit=args.get('limit', 10), node_binary=self.r.config.get('wikiNodeBinary'))
        if action == 'lint':
            result['stale'] = [dict(id=r['id'], sources=r['sources']) for r in records if r['needs_refresh']]
            result['unsourced'] = [r['id'] for r in records if not r['sources'] and not r['origins']]
        else:
            by_id = {r['id']: r for r in records}
            result['items'] = [dict(id=h['slug'], node_id=by_id[h['slug']]['node_id'], version=by_id[h['slug']]['version'],
                                    title=h['title'], score=h['score']) for h in result['items']]
        return dict(engine='llm-wiki', **result)
