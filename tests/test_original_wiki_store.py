"""原 Wiki 存储/导航的独立断言；完整应用权限测试仍待迁移。"""
import os
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]

class OriginalWikiStoreTests(unittest.TestCase):
    def run_case(self, code):
        temporary=ROOT/'build/knowledge-tests'
        temporary.mkdir(parents=True,exist_ok=True)
        code=code.replace('from datanet.knowledge.store import KnowledgeStore','from projects.knowledge_archive.storage.knowledge import KnowledgeStore')
        setup='import tempfile\ntempfile.tempdir='+repr(str(temporary))+'\n'
        result=subprocess.run([sys.executable,'-B','-X','utf8','-c',setup+code],cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

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
