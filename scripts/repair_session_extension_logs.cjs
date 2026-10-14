// Run only after closing the client that owns this home. Original files are backed up.
const fs=require('node:fs/promises'),path=require('node:path'),z=require('node:zlib');
(async()=>{
 const home=path.resolve(process.argv[2]),backup=path.resolve(process.argv[3]);
 if(!process.argv[2]||!process.argv[3]||home===backup)throw Error('Expected separate home and backup directories');
 const allowed=new Set(['datanet/request-tail','datanet/request-recovery']);let files=0,events=0;
 async function visit(dir){for(const item of await fs.readdir(dir,{withFileTypes:true})){const file=path.join(dir,item.name);if(item.isDirectory()){await visit(file);continue;}if(!item.name.endsWith('.jsonl.zstd'))continue;
  const original=await fs.readFile(file);let offset=0,text='',frames=[];while(offset<original.length){const chunk=z.zstdDecompressSync(original.subarray(offset),{info:true});if(!chunk.engine.bytesWritten)throw Error('Invalid zstd frame');offset+=chunk.engine.bytesWritten;frames.push(chunk.buffer.toString('utf8'));text+=chunk.buffer.toString('utf8');}
  let changed=0;const compressed=frames.map(frame=>z.zstdCompressSync(Buffer.from(frame.split('\n').map(line=>{if(!line.trim())return line;const event=JSON.parse(line);if(allowed.has(event.type)&&event.ignorable!==true){event.ignorable=true;changed++;return JSON.stringify(event);}return line;}).join('\n'))));if(!changed)continue;
  const saved=path.join(backup,path.relative(home,file));await fs.mkdir(path.dirname(saved),{recursive:true});await fs.writeFile(saved,original,{flag:'wx'});
  const staging=file+'.datanet-repair';await fs.writeFile(staging,Buffer.concat(compressed),{flag:'wx'});await fs.rename(staging,file);files++;events+=changed;
 }}
 await visit(path.join(home,'sessions'));console.log(JSON.stringify({files,events,backup}));
})().catch(error=>{console.error(error);process.exit(1)});
