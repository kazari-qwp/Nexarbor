"""Local benchmark of a copied paused checkpoint; no application actions or API calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import json,sqlite3,sys
from app.persistence.checkpoints import Checkpoints
from app.persistence.resource_data import read_data,resource_files
from app.persistence.state_journal import checksum
root=Path(__file__).resolve().parents[1];folder=Path(sys.argv[1]).resolve();label=sys.argv[2];runtime=folder/'project/.nexarbor/runs/main'
with TemporaryDirectory(prefix='checkpoint-profile-'+label+'-',dir=root/'build') as temporary:
 home=Path(temporary);source=sqlite3.connect((runtime/'checkpoints.sqlite3').as_uri()+'?mode=ro',uri=True);copy=sqlite3.connect(home/'checkpoints.sqlite3');source.backup(copy);copy.close();source.close()
 t=perf_counter();store=Checkpoints(home);load=perf_counter()-t
 try:
  doc=store.latest();unchanged=[];changed=[]
  for index in range(3):
   t=perf_counter();store.commit(doc);unchanged.append(perf_counter()-t)
   doc['profile_nonce']=index;t=perf_counter();store.commit(doc);changed.append(perf_counter()-t)
   assert store.head_hash==checksum(doc)
  files=[p for p in resource_files(runtime/'created/templates')];t=perf_counter();values={p:read_data(p) for p in files};read_seconds=perf_counter()-t
  report=dict(label=label,source=str(folder),cold_load_seconds=load,unchanged_commit_seconds=unchanged,state_only_commit_seconds=changed,resource_read_seconds=read_seconds,resource_count=len(files),resource_bytes=sum(p.stat().st_size for p in files),hash_matches_original_protocol=True,paid_api_calls=0)
  (folder/('checkpoint-profile-'+label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
 finally:store.close()
