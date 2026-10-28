import test from 'node:test';
import assert from 'node:assert/strict';
import {ModelConnections} from '../adapt/harness/studio/model-connections.mjs';

const policy={model:'deepseek-flash',connection:'harness-default'};

test('an explicit node model and inherited defaults cannot bypass a Flash test policy',async()=>{
 let selections=0;const models=new ModelConnections({project:{read:async()=>({model_settings:{project:{connection:'harness-default',model:'deepseek-v4-pro'}}})},modelPolicy:policy,onModelSelection:()=>{selections++;}});
 await assert.rejects(models.runtime(null,'project'),/测试模型策略拒绝/);
 await assert.rejects(models.runtime({connection:'harness-default',model:'deepseek-v4-pro'},'component'),/测试模型策略拒绝/);
 await assert.rejects(models.runtime({connection:'another-account',model:'deepseek-flash'},'network'),/测试模型策略拒绝/);
 assert.equal(selections,0,'reject before credential access or model execution');
});

test('allowed selection can be audited without exposing credentials',async()=>{
 const events=[],marker=new Error('selection-only test');
 const models=new ModelConnections({project:{read:async()=>({})},modelPolicy:policy,onModelSelection:event=>{events.push(event);throw marker;}});
 await assert.rejects(models.runtime(null,'network'),error=>error===marker);
 assert.deepEqual(events,[{scope:'network',connection:'harness-default',model:'deepseek-flash',stage:'selection'}]);
});


test('official DeepSeek API routes declare native reasoning and conversation capabilities',async()=>{
 const models=new ModelConnections({project:{read:async()=>({})},protect:async value=>value});
 models.read=async()=>({id:'fixture',revision:1,protocol:'openai-completions',base_url:'https://api.deepseek.com/v1',secret:'local-key'});
 const profile=await models.runtime({connection:'fixture',model:'deepseek-flash',reasoning_effort:'low',max_tokens:16000,context_window:600000},'network');
 assert.equal(profile.model.reasoningEfforts.low,'low');
 assert.equal(profile.model.compat.supportsDeveloperRole,false);
 assert.equal(profile.model.compat.requiresReasoningContentOnAssistantMessages,true);
 assert.equal(profile.model.maxTokens,16000);assert.equal(profile.model.contextWindow,600000);
 models.read=async()=>({id:'fixture',revision:1,protocol:'openai-completions',base_url:'http://localhost:8000/v1',secret:'local-key'});
 const other=await models.runtime({connection:'fixture',model:'deepseek-flash'},'network');
 assert.equal(other.model.compat,undefined,'a model name alone cannot impose another provider protocol');
});


test('generation settings do not change a connection model replay identity',async()=>{
 const models=new ModelConnections({project:{read:async()=>({})},protect:async v=>v});
 models.read=async id=>({id,revision:1,protocol:'openai-completions',base_url:'https://api.deepseek.com/v1',secret:'local-key'});
 const a=await models.runtime({connection:'fixture',model:'deepseek-flash'});
 const b=await models.runtime({connection:'fixture',model:'deepseek-flash',max_tokens:16000,context_window:128000});
 assert.equal(a.model.reasoningEffort,'high');assert.equal(b.model.reasoningEffort,'high');
 assert.notEqual(a.signature,b.signature);assert.equal(a.model.provider,b.model.provider);
 const other=await models.runtime({connection:'second',model:'deepseek-flash'});
 // Identity uses the connection record, not a display label or generation settings.
 assert.notEqual(other.model.provider,a.model.provider);
});

test('ordinary and maker request policy permits 10000 and rejects the next request',async()=>{
 const {default:countRequest}=await import('../adapt/harness/native/request-policy.cjs');
 const {default:defaults}=await import('../adapt/harness/framework/agent-defaults.cjs');
 const limit=defaults().max_requests;assert.equal(limit,10000);
 const entry={steps:9999};assert.equal(countRequest(entry,limit),10000);
 assert.throws(()=>countRequest(entry,limit),/10000/);assert.equal(entry.steps,10000);
});
