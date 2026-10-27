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
