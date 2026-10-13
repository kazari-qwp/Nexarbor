const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const nativeRoot=process.env.DATANET_NATIVE_MODULES??path.join(process.env.LOCALAPPDATA,'Programs','DeepSeek Harness','resources','app.asar','dsh','node_modules');
const productRoot=path.resolve(__dirname,'..');
const testRoot=process.env.DATANET_TEST_TEMP??path.join(productRoot,'build','test-data');
require('node:fs').mkdirSync(testRoot,{recursive:true});
const requireNative=name=>require(path.join(nativeRoot,'@deepseek-ai',name));
(async()=>{
  const include=requireNative('cordis-plugin-include'),yaml=require(path.join(nativeRoot,'js-yaml'));
  const patches=yaml.load(await fs.readFile(productRoot+'/cordis.patch.yml','utf8'),{schema:include.entryListSchema});
  const warnings=[];
  const config=include.applyEntryPatches([{id:'agent-loop',name:'@deepseek-ai/dsh-agent-loop',config:{agents:[]}},{id:'agent-loop-invariant',name:'@deepseek-ai/dsh-agent-loop/invariant'}],patches,(message,...args)=>warnings.push([message,args]));
  assert.deepEqual(warnings,[]);
  assert.equal(config.find(x=>x.id==='agent-loop').disabled,true);
  assert.equal(config.find(x=>x.id==='agent-loop-invariant').disabled,true);
  assert.equal(config.filter(x=>!x.disabled&&x.name.endsWith('/agent-loop')).length,1);
  assert.equal(config.filter(x=>!x.disabled&&x.name.endsWith('/agent-loop/invariant')).length,1);
  const manifest=JSON.parse(await fs.readFile(productRoot+'/package.json','utf8'));
  for(const entry of config.filter(x=>!x.disabled&&x.name.startsWith('datanet-harness/'))){
    const exported='.'+entry.name.slice('datanet-harness'.length);assert.ok(manifest.exports[exported]);await fs.access(path.join(productRoot,manifest.exports[exported]));
  }
  console.log('PASS native bundle patch composition: no warnings; exactly one active tail driver and corresponding invariant, both exported');
})().catch(error=>{console.error(error);process.exitCode=1;});
