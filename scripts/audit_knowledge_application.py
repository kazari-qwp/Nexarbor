"""独立读取真实集合文件，核对原资料库数据与版本；不运行 Agent。"""
from pathlib import Path
from hashlib import sha256
import json,sqlite3,sys
from app.studio.project import WorkbenchProject
from adapt.files.storage_paths import storage_path
root=Path(__file__).resolve().parents[1];folder=Path(sys.argv[1]).resolve();project=WorkbenchProject(folder/'project/.nexarbor/runs/main',folder/'project')
try:
 records=[];versions=[];refs=[];collections=[];pending=[]
 for node in project.backend.network:
  if node.node_type not in ('knowledge_collection','knowledge_catalog'):continue
  directory=node.saver.path
  db=sqlite3.connect((directory/'catalog.sqlite3').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  try:
   if node.node_type=='knowledge_catalog':
    pending=[dict(row) for row in db.execute("SELECT id,status FROM intakes WHERE status IN ('pending','partial')")];continue
   local=[dict(row) for row in db.execute('SELECT * FROM collections')];collections.extend(dict(row,node_id=node.info.node_id) for row in local);types={row['id']:row['storage'] for row in local}
   for row in db.execute('SELECT * FROM records'):
    item=dict(row);item.update(storage=types[item['collection_id']],directory=str(directory),node_id=node.info.node_id,body=json.loads(storage_path(directory/item['raw_path']).read_text(encoding='utf-8')))
    item['intake_origins']=db.execute('SELECT count(*) FROM record_intakes WHERE record_id=?',(item['id'],)).fetchone()[0];records.append(item)
   for row in db.execute('SELECT * FROM versions'):
    item=dict(row);file=storage_path(directory/item['raw_path']);data=file.read_bytes();item.update(valid=sha256(data).hexdigest()==item['hash'],body=json.loads(data));versions.append(item)
   refs.extend(dict(row) for row in db.execute('SELECT * FROM references_to_sources'))
  finally:db.close()
 oracle=json.loads(Path('E:/DataNet-模块化成品/build/agent-learning-20261020/evaluator/knowledge-original-input-oracle.json').read_text(encoding='utf-8'))
 active=[r for r in records if not r['deleted']];observations=[r['body'] for r in active if r['storage']=='sqlite' and isinstance(r['body'],dict) and 'event_id' in r['body']];actual={r['event_id']:r for r in observations};expected=oracle['updated']['records_by_id']
 mismatch=[key for key in actual.keys()|expected.keys() if actual.get(key)!=expected.get(key)]
 catalog=[r['body'] for r in active if r['storage']=='csv' and isinstance(r['body'],dict) and 'source_id' in r['body']];byid={r['source_id']:r for r in catalog}
 def normalize(text):return text.replace('\r\n','\n').replace('\r','\n').lstrip('\ufeff').rstrip('\n')
 def strings(value):
  if isinstance(value,str):yield value
  elif isinstance(value,dict):
   for part in value.values():yield from strings(part)
  elif isinstance(value,list):
   for part in value:yield from strings(part)
 def matching(text):return [dict(id=row['record_id'],version=row['version']) for row in versions if isinstance(row['body'],str) and normalize(row['body'])==normalize(text)]
 docs={name:matching((folder/'project/workspace/imports/documents'/name).read_text(encoding='utf-8-sig')) for name in oracle['documents']}
 requirements={key:matching(max(strings(value),key=len)) for key,value in oracle['requirements'].items()}
 current={r['id']:r for r in records};stale=[row for row in refs if row['source_id'] not in current or current[row['source_id']]['deleted'] or row['source_version']!=current[row['source_id']]['version']]
 wal=[dict(id=r['id'],version=r['version'],origins=r['intake_origins']) for r in active if isinstance(r['body'],str) and 'Write-Ahead Logging' in r['body'] and len(r['body'])>30000]
 checks={'all_481_observations_exact':len(observations)==481 and len(actual)==481 and not mismatch,'catalog_14_rows_exact_with_leading_zeros':len(catalog)==14 and all(byid.get(row['source_id'])==row for row in oracle['catalog']),'all_13_verbatim_originals':len(docs)==13 and all(docs.values()),'v1_and_v2_requirements_preserved':all(requirements.values()),'all_record_version_hashes_intact':all(row['valid'] for row in versions),'no_stale_current_source_references':not stale,'duplicate_wal_shares_record_and_origins':any(row['origins']>=2 for row in wal),'no_pending_intakes':not pending}
 evidence=json.loads((folder/'knowledge-evidence.json').read_text(encoding='utf-8'))
 phases={item['phase']:item for item in evidence['phases']}
 checks.update(readonly_phases_2_4_5_6_unchanged=all(phases.get(n,{}).get('knowledge_image_changed') is False for n in (2,4,5,6)),restart_storage_image_and_session_unchanged=evidence.get('checkpoint_knowledge_image_equal') is True and evidence.get('session_before')==evidence.get('session_after'),six_original_phases_completed=all(phases.get(n,{}).get('status')=='completed' for n in range(1,7)),no_uncertain_operations=not project.backend.store.pending())
 transcript=json.loads((folder/'phase-6-transcript.json').read_text(encoding='utf-8'))['messages'];last=max(i for i,m in enumerate(transcript) if m['role']=='user')
 calls=[block for m in transcript[last:] for block in m.get('content',[]) if isinstance(block,dict) and block.get('type')=='tool-call'];history=json.loads((folder/'phase-6-after.json').read_text(encoding='utf-8'))['sessions']['root']['tool_history']
 named=[dict(description=history[block['name']]['definition']['description'],arguments=json.loads(block['arguments'])) for block in calls]
 checks['real_semantic_and_keyword_queries_and_versioned_wiki_navigation']=sum('kb_search' in c['description'] and c['arguments'].get('semantic') is True for c in named)>=2 and any('kb_search' in c['description'] and not c['arguments'].get('semantic') for c in named) and any('kb_fetch' in c['description'] and c['arguments'].get('view')=='window' and 'version' in c['arguments'] for c in named) and any('kb_fetch' in c['description'] and c['arguments'].get('view')=='section' for c in named)
 report=dict(paid_api_calls=0,checks=checks,observations=len(observations),duplicates=len(observations)-len(actual),mismatch_ids=mismatch[:10],collections=collections,versions=len(versions),documents=docs,requirements=requirements,stale_sources=stale,pending_intakes=pending,wal_dedup=wal,checkpoint=project.backend.store.stats(),uncertain_operations=project.backend.store.pending(),phase='partial-stage3' if not (folder/'knowledge-evidence.json').exists() else json.loads((folder/'knowledge-evidence.json').read_text(encoding='utf-8')).get('status'))
 report.update(passed=all(checks.values()),navigation_calls=named,phase_costs=evidence['phases'],total_usage=evidence['usage'])
 (folder/'independent-data-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({key:report[key] for key in ['checks','observations','duplicates','mismatch_ids','versions','uncertain_operations']},ensure_ascii=False))
finally:project.close()
