"""Force-kill owned subprocesses: committed and uncommitted SQLite WAL writes."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from datanet.core.checkpoints import Checkpoints
ROOT=Path(__file__).resolve().parents[1]
CHILD=r"""
import sys
from pathlib import Path
from datanet.core.checkpoints import Checkpoints
from datanet.core.state_journal import canonical,checksum,diff
s=Checkpoints(Path(sys.argv[1]));s.begin('interrupted','save')
value={'counter':2}
if sys.argv[2]=='committed':s.commit(value,'interrupted')
else:
 s.db.execute('BEGIN IMMEDIATE')
 s.db.execute('INSERT INTO commits(parent_hash,state_hash,delta,operation_id) VALUES (?,?,?,?)',(s.head_hash,checksum(value),canonical(diff(s.latest(),value)),'interrupted'))
print('READY',flush=True)
sys.stdin.read()
"""
class CrashTests(unittest.TestCase):
    def crash(self,mode):
        with tempfile.TemporaryDirectory() as folder:
            s=Checkpoints(Path(folder));s.commit({'counter':0});s.commit({'counter':1});s.close()
            env=dict(os.environ,PYTHONPATH=str(ROOT/'python'))
            child=subprocess.Popen([sys.executable,'-u','-c',CHILD,folder,mode],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'READY')
                child.kill();child.wait(timeout=10)
                s=Checkpoints(Path(folder))
                try:
                    self.assertEqual(s.latest(),{'counter':2 if mode=='committed' else 1})
                    self.assertEqual(bool(s.pending()),mode!='committed')
                finally:s.close()
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                child.stdin.close();child.stdout.close();child.stderr.close()
    def test_kill_after_commit_recovers_latest_increment(self):self.crash('committed')
    def test_kill_inside_sqlite_transaction_discards_torn_increment(self):self.crash('uncommitted')

if __name__=='__main__':unittest.main()
