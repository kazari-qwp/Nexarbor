import test from 'node:test';import assert from 'node:assert/strict';
import {inspectNetwork} from '../../../adapt/harness/studio/makers/network-inspection.mjs';
import {Advisors,adviceTools} from '../../../adapt/harness/studio/makers/advisors.mjs';

function fixture(){
 const meta={channels:['info'],threshold:0,multiplier:0,attributes:{channel_mode:'deny',relation:'road'}};
 const node={node_id:'a',name:'甲',description:'讨论成员',type:'agent',management_parent_id:null,divergence:-1,module_strength:0,
  parameters:{file_path:'private/a.md',creation_options:{}},modules:{'demo.module':{config:{message:'CONFIG_BODY',options:{nested:['FULL_CONFIG']}},state:{receipts:['RUNTIME_RECEIPT']},access:{channels:['info'],strength:2}}},
  connections:{interfaces:[{target_node_id:'b',metadata:meta},{target_node_id:'b',metadata:{...meta,channels:[]}}]},offered_tools:[],inputs:{persona:{context:[{id:'memory',text:'PRIVATE_BODY'}]}},execution:{executor:'harness',channels:['info']},context_cursor:null};
 const child={...structuredClone(node),node_id:'b',name:'乙',type:'subnode',description:'',parameters:{parent_id:'a',use_parent_links:false,share_links:true},connections:{interfaces:[]}};
 return {document:{network:{version:8,nodes:[node,child],signals:{old_run:{events:['SIGNAL_HISTORY']}},delegations:[{source:'a',target:'b'}],repeat_unit_count:2,repeat_unit:['b']},files:{'private/a.md':'FILE_BODY'}},resources:{'demo.module':{release:{manifest:{name:'通用模块',description:'模块说明'}}}},target:{kind:'network',name:'全网'},selection:{nodes:['a'],edges:['a|1']}};
}

test('concise keeps every node, parallel edge, channel filter, ownership and declaration without state bodies',()=>{
 const snapshot=fixture(),before=structuredClone(snapshot),result=inspectNetwork(snapshot,'fixed'),edges=result.edges.map(edge=>({...result.edge_defaults,...edge}));assert.equal(result.response_format,'concise');assert.equal(result.nodes.length,2);assert.equal(edges.length,2);assert.equal(edges[0].threshold,0);assert.equal(edges[0].multiplier,0);assert.equal(edges[0].attributes.channel_mode,'deny');assert.deepEqual(edges[1].channels,[]);assert.equal(edges[1].id,'a|1');
 assert.deepEqual(result.nodes[1].parameters,{parent_id:'a',use_parent_links:false,share_links:true});assert.equal(result.nodes[0].module_strength,0);assert.ok(!('description' in result.nodes[1]));assert.ok(!('management_parent_id' in result.nodes[0]));assert.deepEqual(result.delegations,snapshot.document.network.delegations);assert.equal(result.repeat_unit_count,2);assert.deepEqual(result.repeat_unit,['b']);assert.deepEqual(result.module_catalog,[{id:'demo.module',name:'通用模块'}]);
 for(const omitted of ['CONFIG_BODY','FULL_CONFIG','RUNTIME_RECEIPT','PRIVATE_BODY','SIGNAL_HISTORY','FILE_BODY'])assert.ok(!JSON.stringify(result).includes(omitted),omitted);assert.deepEqual(snapshot,before);
});

test('node concise exposes module names and access; detailed preserves exact node and incoming links',()=>{
 const snapshot=fixture(),brief=inspectNetwork(snapshot,'fixed',{node:'b'}),full=inspectNetwork(snapshot,'fixed',{node:'b',response_format:'detailed'});
 assert.deepEqual(brief.node.modules['demo.module'],{name:'通用模块',access:{channels:['info'],strength:2}});assert.ok(!brief.node.parameters.file_path);assert.equal(brief.edges.length,2);assert.match(brief.detail_hint,/detailed/);assert.deepEqual(full.node,snapshot.document.network.nodes[1]);assert.equal(full.incoming.length,2);assert.equal(full.snapshot,brief.snapshot);assert.ok(JSON.stringify(full).includes('RUNTIME_RECEIPT'));full.node.name='changed';assert.equal(snapshot.document.network.nodes[1].name,'乙');
});

test('edge defaults reconstruct each original rule, including exceptions and omitted optional metadata',()=>{
 const snapshot=fixture(),node=snapshot.document.network.nodes[0];node.connections.interfaces.push({target_node_id:'b'},{target_node_id:'a',metadata:{threshold:3,multiplier:2,channels:['tools'],attributes:{channel_mode:'allow',nested:{flag:false}}}});
 const result=inspectNetwork(snapshot,'fixed');for(let i=0;i<node.connections.interfaces.length;i++){
  const {id,source,target,...overrides}=result.edges.find(edge=>edge.id==='a|'+i),actual={...result.edge_defaults,...overrides},meta=node.connections.interfaces[i].metadata??{};
  assert.deepEqual(actual,{threshold:0,multiplier:1,channels:[],attributes:{},...meta});assert.equal(source,'a');assert.equal(target,node.connections.interfaces[i].target_node_id);
 }
 const empty=fixture();empty.document.network.nodes=[];const brief=inspectNetwork(empty,'fixed');assert.deepEqual(brief.edges,[]);assert.ok(!('edge_defaults' in brief));assert.deepEqual(brief.nodes,[]);
});

test('whole-network detailed retains graph properties and preset bodies; preset concise also preserves its topology',()=>{
 const snapshot=fixture();snapshot.preset={name:'预设',document:structuredClone(snapshot.document)};const brief=inspectNetwork(snapshot,'fixed'),full=inspectNetwork(snapshot,'fixed',{response_format:'detailed'});
 assert.equal(brief.preset.nodes.length,2);assert.equal(brief.preset.edges.length,2);assert.ok(!JSON.stringify(brief).includes('FILE_BODY'));assert.deepEqual(full.nodes,snapshot.document.network.nodes);assert.deepEqual(full.network_properties.signals,snapshot.document.network.signals);assert.deepEqual(full.files,['private/a.md']);assert.deepEqual(full.preset.document,snapshot.preset.document);
 assert.throws(()=>inspectNetwork(snapshot,'fixed',{response_format:'unknown'}),/response_format/);assert.throws(()=>inspectNetwork(snapshot,'fixed',{node:'missing'}),/不在本轮快照/);
});

test('registered tool routes both modes through the same fixed snapshot and keeps file paging separate',async()=>{
 const advisor=Object.create(Advisors.prototype),snapshot=fixture();advisor.makers={projectObservations:{uses:()=>false,clear:()=>{}}};advisor.jobs=new Map([['job',{status:'running',snapshot:{id:'fixed'},tool_events:[]}]]);advisor.getSnapshot=async id=>{assert.equal(id,'fixed');return structuredClone(snapshot);};
 const query=arguments_=>advisor.tool({task:'job',tool:'inspect_network',arguments:arguments_});const brief=await query({node:'a'}),full=await query({node:'a',response_format:'detailed'});assert.equal(brief.snapshot,full.snapshot);assert.ok(!brief.node.inputs);assert.deepEqual(full.node.inputs,snapshot.document.network.nodes[0].inputs);
 assert.deepEqual(await query({file:'private/a.md',start_line:1,line_count:1}),{file:'private/a.md',total_lines:1,text:'FILE_BODY'});await assert.rejects(query({file:'private/a.md',response_format:'wrong'}),/response_format/);await assert.rejects(query({file:'outside'}),/不在本轮快照/);
 assert.ok(!adviceTools.some(t=>t.name==='inspect_network'));assert.ok(adviceTools.some(t=>t.name==='read_network_text'));advisor.jobs.get('job').status='completed';await assert.rejects(query({response_format:'detailed'}),/已停止/);
});
