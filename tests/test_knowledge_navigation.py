"""Structural retrieval must preserve conditions, exact original spans and versions."""
import importlib.util
from pathlib import Path
import unittest
import test_knowledge_base as base
from test_knowledge_helpers import case

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('document_structure_under_test',ROOT/'extensions/storage/capabilities/document_structure/python/datanet/document_structure/structure.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
DocumentStructure=module.DocumentStructure


class StructureTests(unittest.TestCase):
    def test_unstructured_fragment_has_no_invented_sections(self):
        text='2026-10-15，李工：先保留原始采样。\n来源：现场聊天记录。'
        tree=DocumentStructure(text)
        outline=tree.outline()
        self.assertFalse(outline['has_structure'])
        self.assertEqual(outline['total_sections'],1)
        fragment=tree.context(view='section')
        self.assertEqual(fragment['content'],text)
        self.assertEqual(fragment['ancestor_context'],[])
        self.assertEqual(fragment['children'],[])

    def test_real_markdown_hierarchy_and_exact_positions(self):
        text='---\ntitle: Not a heading\n---\n# Rules\nOnly a single host.\n## Same\nConcurrent readers are allowed.\n```md\n# Not a heading\n```\n> # Also not a section\n## Same\nExceptions apply.\n\nSetext title\n------------\n| Name | Limit |\n| ---- | ----- |\n| A | 1 |\n'
        tree=DocumentStructure(text)
        self.assertEqual([s['title'] for s in tree.sections[1:]],['Rules','Same','Same','Setext title'])
        same=[s for s in tree.sections if s['title']=='Same']
        self.assertNotEqual(same[0]['section_id'],same[1]['section_id'])
        self.assertEqual(same[0]['parent_id'],tree.sections[1]['section_id'])
        child=tree.context(view='section',section_id=same[0]['section_id'])
        self.assertIn('Only a single host.', ''.join(x['content'] for x in child['ancestor_context']))
        self.assertNotIn('Exceptions apply.',child['content'])
        self.assertEqual(child['next']['section_id'],same[1]['section_id'])
        table=tree.context(view='section',section_id=tree.sections[-1]['section_id'])
        self.assertIn('| Name | Limit |',table['content']);self.assertIn('| A | 1 |',table['content'])
        location=child['location'];self.assertEqual(text[location['start_char']:location['end_char']],child['content'])

    def test_ambiguous_passages_never_get_a_fabricated_location(self):
        text='# First\nRepeated sentence.\n# Second\nRepeated sentence.\n'
        tree=DocumentStructure(text)
        self.assertIsNone(tree.locate('Repeated sentence.'))
        position=text.rindex('Repeated sentence.')
        found=tree.locate('Repeated sentence.',position,position+len('Repeated sentence.'))
        self.assertEqual(tree.at(found['start_char'])['title'],'Second')
        self.assertIsNone(tree.locate('missing passage'))

    def test_bounded_pages_reassemble_the_original_section(self):
        text='# Parent\nSingle-host only.\n## Child\n'+('A long paragraph.\n'*50)+'## Other\nUnrelated.\n'
        tree=DocumentStructure(text);id=tree.sections[2]['section_id'];offset=0;parts=[]
        while True:
            page=tree.context(view='section',section_id=id,offset=offset,max_chars=80)
            self.assertLessEqual(len(page['content'])+sum(len(x['content']) for x in page['ancestor_context']),80)
            parts.append(page['content'])
            if page['next_offset'] is None:break
            self.assertGreater(page['next_offset'],offset);offset=page['next_offset']
        section=tree.section(id)
        expected=''.join(tree.lines[section['start_line']-1:section['end_line']])
        self.assertEqual(''.join(parts),expected)
        self.assertIsNotNone(tree.outline(limit=1)['next_offset'])


class KnowledgeNavigationTests(unittest.TestCase):
    run_case=base.KnowledgeBaseTests.run_case

    def test_tools_navigate_history_without_mutating_records(self):
        self.run_case(case("""
app.invoke('root','kb_task',dict(content='核查文档结构'))
collection=app.invoke('root','kb_create_node',dict(name='原文',storage='rag'))
text='# Parent\\nOnly one host.\\n## Rules\\nReaders and writers may overlap.\\n## Exceptions\\nKeep this exception.\\n'
record=app.invoke('root','kb_store',dict(collection=collection['id'],content=text,key='doc'))
outline=app.invoke('root','kb_fetch',dict(id=record['id'],view='outline',limit=2))
assert 'content' not in outline and outline['is_excerpt'] and outline['next_fetch']['version']==1
second=app.invoke('root','kb_fetch',outline['next_fetch'])
section=next(h for h in second['outline'] if h['title']=='Rules')
read=app.invoke('root','kb_fetch',section['read'])
assert 'Readers and writers' in read['content']
assert 'Only one host.' in ''.join(x['content'] for x in read['ancestor_context'])
assert app.invoke('root','kb_fetch',read['next']['read'])['section']['title']=='Exceptions'
app.invoke('root','kb_update',dict(id=record['id'],content=text.replace('Only one host.','Version 2 changes.'),expected_version=1))
historical=app.invoke('root','kb_fetch',section['read'])
assert historical['version']==1 and 'Only one host.' in ''.join(x['content'] for x in historical['ancestor_context'])
assert app.invoke('root','kb_fetch',historical['full_fetch'])['content']==text
assert app.invoke('root','kb_fetch',dict(id=record['id']))['version']==2
"""))

    def test_context_views_keep_the_collection_graph_permission(self):
        self.run_case(case("""
app.invoke('root','kb_task',dict(content='只查看被授权资料'))
collection=app.invoke('root','kb_create_node',dict(name='原文',storage='rag'))
record=app.invoke('root','kb_store',dict(collection=collection['id'],content='# Secret\\nPrivate text.'))
helper=app.invoke('root','datanet_spawn_helper',dict(components=['wiki']))
actor=helper['node_id']
assert app.invoke(actor,'kb_fetch',dict(id=record['id'],view='outline'))['outline']
node=backend.network.nodes[actor];node.interfaces=[e for e in node.interfaces if e.target_node_id!=collection['node_id']]
for view,args in [('outline',{}),('section',{'section_id':'L1'}),('window',{'start_line':1})]:
    try:app.invoke(actor,'kb_fetch',dict(id=record['id'],view=view,**args))
    except PermissionError:pass
    else:raise AssertionError('Navigation bypassed graph read permission')
"""))

    def test_passages_keep_best_match_and_do_not_duplicate_document_votes(self):
        self.run_case("""
import tempfile,hashlib
from types import SimpleNamespace
from datanet.knowledge.store import KnowledgeStore
with tempfile.TemporaryDirectory() as folder:
    store=KnowledgeStore(folder);collection=store.create_collection('Sources','rag')
    a=store.store(collection['id'],'# Rules\\nSame host only.\\n## Read\\nBest A passage.\\n',key='a')
    b=store.store(collection['id'],'# Details\\nBest B passage.\\nLower B passage.\\n',key='b')
    with store.connection() as db:db.execute("update records set index_state='ready'")
    def hit(record,quote,score,id):
        text=record['content'];start=text.index(quote)
        return dict(chunk_id=id,text=quote,score=score,start_char=start,end_char=start+len(quote),metadata={'file_name':record['id']+'.md','source_sha256':hashlib.sha256(text.encode()).hexdigest()})
    passages=[hit(a,'Best A passage.',.99,'a-best'),hit(b,'Best B passage.',.9,'b-best'),hit(b,'Lower B passage.',.5,'b-lower')]
    store.indexes[collection['id']]=SimpleNamespace(search=lambda *a,**k:SimpleNamespace(items=passages))
    store.embedding_config={'test':True}
    result=store.search('unseen-semantic-intent',collection=collection['id'],semantic=True)
    assert [r['id'] for r in result['items']]==[a['id'],b['id']]
    assert result['items'][1]['snippet']=='Best B passage.'
    match=result['items'][0]['matches'][0]
    assert match['location_verified'] and match['section']['title']=='Read'
    context=store.fetch(**match['section_fetch'])
    assert 'Same host only.' in ''.join(r['content'] for r in context['ancestor_context'])
    # A reader must not attach stale indexed text to a newly published source.
    passages[0]['metadata']['source_sha256']='invalid-old-hash'
    result=store.search('unseen-semantic-intent',collection=collection['id'],semantic=True)
    assert all(r['id']!=a['id'] for r in result['items'])
""")

if __name__=='__main__':unittest.main()
