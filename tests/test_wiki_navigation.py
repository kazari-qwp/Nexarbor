"""Wiki entries retain exact originals, bounded links and collection permissions."""
import unittest
import test_knowledge_base as base
from test_knowledge_helpers import case


class WikiNavigationTests(unittest.TestCase):
    run_case=base.KnowledgeBaseTests.run_case

    def test_links_aliases_ambiguity_paging_and_history(self):
        self.run_case('''
import tempfile
from datanet.knowledge.store import KnowledgeStore
with tempfile.TemporaryDirectory() as folder:
    s=KnowledgeStore(folder);c=s.create_collection('Wiki','wiki');outside=s.create_collection('Other','wiki')
    beta=s.store(c['id'],'---\\naliases: [Beta, Shared]\\n---\\n# Beta page\\n## Details\\nOriginal detail.',key='b.md')
    duplicate=s.store(c['id'],'# Shared\\nAmbiguous name.',key='duplicate')
    secret=s.store(outside['id'],'# Secret title\\nPrivate.',key='hidden')
    text='# Alpha\\n[[Beta#Details|Read details]] [[Shared]] [[missing]] [[hidden]]\\n`[[not-a-link]]`\\n```md\\n[[also-not-a-link]]\\n```\\n[local](b.md) [external](https://example.com)'
    alpha=s.store(c['id'],text,key='a')
    links=s.fetch(alpha['id'],view='links',limit=2)
    assert links['total_links']==5,links
    first=links['links'][0];assert first['status']=='resolved' and first['id']==beta['id'] and first['anchor']=='Details'
    assert first['read']['version']==1 and first['read']['view']=='outline'
    assert links['links'][1]['status']=='ambiguous' and len(links['links'][1]['candidates'])==2
    rest=s.fetch(**links['links_next_fetch'])
    assert all(x['status']=='unresolved' for x in rest['links'])
    assert all('fetch' not in x for x in rest['links'])
    tail=s.fetch(**rest['links_next_fetch'])
    assert tail['links'][0]['id']==beta['id'] and tail['links_next_fetch'] is None
    assert s.fetch(alpha['id'])['content']==text
    s.update(beta['id'],'# New title\\nNew detail.',expected_version=1)
    s.update(alpha['id'],'# Alpha v2\\nNew body.',expected_version=1)
    historical=s.fetch(alpha['id'],version=1)
    assert historical['content']==text and historical['page']['title']=='Alpha'
    # Old source page links resolve when read, not to an invented historical target.
    old_link=next(x for x in historical['links'] if x['target']=='b.md')
    assert old_link['read']['version']==2 and historical['link_versions']=='target_current_at_read'
    assert s.fetch(**first['read'])['version']==1
    s.delete(beta['id'],expected_version=2)
    assert next(x for x in s.fetch(alpha['id'],version=1)['links'] if x['target']=='b.md')['status']=='unresolved'
    restored=KnowledgeStore(folder)
    assert restored.fetch(alpha['id'])['page']['title']=='Alpha v2'
''')

    def test_unified_entries_and_links_do_not_grant_access(self):
        self.run_case(case('''
app.invoke('root','kb_task',dict(content='Read links'))
c=app.invoke('root','kb_create_node',dict(name='Wiki',storage='wiki'))
target=app.invoke('root','kb_store',dict(collection=c['id'],content='# Target\\nUnstructured fragment.',key='target'))
page=app.invoke('root','kb_store',dict(collection=c['id'],content='# Entry\\n[[target]]',key='entry'))
helper=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))['node_id']
read=app.invoke(helper,'kb_fetch',dict(id=page['id'],view='links'))['links'][0]['read']
fetched=app.invoke(helper,'kb_fetch',read)
assert fetched['id']==target['id']
assert fetched['evidence']==dict(node_id=c['node_id'],locator=target['id'],version=1)
app.invoke(helper,'task_document_write',dict(content='Checked target',sources=[fetched['evidence']]))
hit=app.invoke(helper,'kb_search',dict(query='Unstructured',collection=c['id']))['items'][0]
assert hit['entry']['wiki_link']=='[['+target['id']+']]' and hit['entry']['read']['version']==1
node=backend.network.nodes[helper];node.read_interfaces=[e for e in node.read_interfaces if e.target_node_id!=c['node_id']]
try:app.invoke(helper,'kb_fetch',read)
except PermissionError:pass
else:raise AssertionError('Previously read link granted permission after revocation')
assert app.invoke(helper,'kb_search',dict(query='Unstructured'))['items']==[]
'''))

    def test_invalid_frontmatter_cannot_poison_recovery(self):
        self.run_case('''
import tempfile
from yaml import YAMLError
from datanet.knowledge.store import KnowledgeStore
with tempfile.TemporaryDirectory() as folder:
    store=KnowledgeStore(folder);collection=store.create_collection('Pages','wiki')
    try:store.store(collection['id'],'---\\naliases: [unterminated\\n---\\nOriginal.')
    except YAMLError:pass
    else:raise AssertionError('Invalid Wiki metadata accepted')
    restored=KnowledgeStore(folder)
    assert restored.search(collection=collection['id'])['total']==0
''')


if __name__=='__main__':unittest.main()
