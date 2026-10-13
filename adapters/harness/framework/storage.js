// Route native root Sessions to isolated graph storage, retaining legacy owners.
import path from 'node:path';
import {existsSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';

export function networkDirectory(base,sessionId){
  const scoped=path.join(base,'networks',Buffer.from(sessionId).toString('hex'));
  if(existsSync(path.join(scoped,'checkpoints.sqlite3')))return scoped;
  const legacy=path.join(base,'checkpoints.sqlite3');
  if(!existsSync(legacy))return scoped;
  const db=new DatabaseSync(legacy,{readOnly:true});
  try{
    const row=db.prepare('SELECT document FROM checkpoints ORDER BY id DESC LIMIT 1').get();
    if(row&&JSON.parse(row.document).agents?.root?.session_id===sessionId)return base;
  }finally{db.close();}
  return scoped;
}
