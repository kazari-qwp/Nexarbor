"""Kill only an owned fixture process during/after a node transaction."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from app.runtime.backend import Backend

ROOT=Path(__file__).resolve().parents[1]
CHILD=r'''
import asyncio,sys
from app.runtime.backend import Backend
from domain.agent import MarkdownAgentNode
from domain.core import Node, NodeInfo, Link
b=Backend(sys.argv[1]);mode=sys.argv[2]
(b.directory/'b.md').write_text('OLD',encoding='utf-8')
b.network.add(MarkdownAgentNode(NodeInfo('b','before'),b.directory/'b.md'))
b.network.add(Node(NodeInfo('c','before')))
b.network.get('root').links.add(Link('b','red'))
b.agents['b']={'session_id':'session-b'}
count=1
class Port:
 async def capture(self,bindings):return {n:{'adapter':'fixture','session_id':s,'event_count':count} for n,s in bindings.items()}
b.context_port=Port();b.save()
async def run():
 global count
 async with b.node_locks.transaction(['b']):
  b.network.get('b').info.name='after';b.network.get('b').dataer.write('NEW');count=2
  b.network.get('c').info.name='independent'
  if mode!='inside-no-save':b.save()
  if mode.startswith('inside'):print('READY',flush=True);sys.stdin.read()
 print('READY',flush=True);sys.stdin.read()
asyncio.run(run())
'''


class NodeLockCrashTests(unittest.TestCase):
    def crash(self,mode):
        with tempfile.TemporaryDirectory(prefix='.node-crash-',dir=ROOT/'build') as folder:
            env=dict(os.environ,PYTHONPATH=str(ROOT))
            child=subprocess.Popen([sys.executable,'-u','-c',CHILD,folder,mode],cwd=ROOT,env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                line=child.stdout.readline().strip()
                if line!='READY':self.fail(line+' '+child.stderr.read())
                child.kill();child.wait(timeout=10)
                backend=Backend(folder)
                try:
                    expected='NEW' if mode=='committed' else 'OLD'
                    self.assertEqual(backend.network.get('b').dataer.read(),expected)
                    self.assertEqual(backend.network.get('b').info.name,'after' if mode=='committed' else 'before')
                    self.assertEqual(backend.network.get('c').info.name,'before' if mode=='inside-no-save' else 'independent')
                    self.assertEqual(backend.agents['b']['context_cursor']['event_count'],2 if mode=='committed' else 1)
                    self.assertEqual(backend.node_locks.exclusive,{})
                finally:backend.close()
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                child.stdin.close();child.stdout.close();child.stderr.close()

    def test_crash_during_transaction_keeps_before_image_and_other_commits(self):self.crash('inside')
    def test_lock_backup_is_durable_before_any_other_save(self):self.crash('inside-no-save')
    def test_crash_after_transaction_keeps_new_node_record_and_cursor(self):self.crash('committed')


if __name__=='__main__':unittest.main()
