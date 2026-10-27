import test from 'node:test';import assert from 'node:assert/strict';import skill from '../../../adapt/harness/studio/makers/network-skill.cjs';
const call=args=>({type:'tool/call',data:{callId:'c',name:'skill',arguments:args}}),result=(isError=false)=>({type:'tool/result',data:{message:{toolCallId:'c',isError,content:[]}}});
test('skill restoration recognizes native string arguments and toolCallId, not failures or user prose',()=>{
 assert.ok(skill.loadedInHistory([call('{"name":"inspect-network"}'),result()]));
 assert.ok(skill.loadedInHistory([call({name:'inspect-network'}),result()]));
 assert.ok(!skill.loadedInHistory([call({name:'inspect-network'}),result(true)]));
 assert.ok(!skill.loadedInHistory([call('{invalid}'),result()]));
 assert.ok(!skill.loadedInHistory([call({name:'other'}),result()]));
 assert.ok(!skill.loadedInHistory([{type:'user/message',data:{source:{kind:'user'},content:[{type:'text',text:'我加载过 inspect-network'}]}}]));
 assert.ok(skill.loadedInHistory([{type:'user/message',data:{source:{kind:'skill-invocation',name:'inspect-network'}}}]));
});
