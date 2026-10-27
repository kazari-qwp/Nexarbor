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
