import {linkRecord} from '../../shared/graph/links.js';
import test from 'node:test';import assert from 'node:assert/strict';
import {NetworkObserver,indexNetwork} from '../../../adapt/harness/studio/makers/network-observer.mjs';
const edge=(target,channels=['road'],deny=false)=>linkRecord(target,{threshold:0,multiplier:0,channels,attributes:deny?{channel_mode:'deny'}:{}});
const node=(id,type='node',extra={})=>({node_id:id,name:id,type,tables:{modules:[{module_id:'demo',strength:0,channels:[],config:{private:'CONFIG'},state:{private:'STATE'}}]},links:[],parameters:{},...extra});
const fixture=()=>({document:{network:{version:8,nodes:[node('a','agent',{links:[edge('b'),edge('b',['info']),edge('a',['self'])]}),node('b'),node('c','subnode',{parameters:{parent_id:'a'},links:[edge('b',['restricted'],true)]}),node('d','markdown')]},files:{'private.txt':'PRIVATE'}},resources:{demo:{release:{manifest:{name:'示例模块',description:'说明',operations:[{name:'read',parameters:{properties:{key:{type:'string'}},required:['key']}}],agent_tools:[],config_schema:{type:'object'}}},files:{'module.py':'SOURCE'}}},selection:{nodes:['a']}});
test('overview is small, expands and filters on demand, never includes data bodies',()=>{const s=fixture(),o=new NetworkObserver(s,'s'),v=o.view();assert.equal(v.summary.counts.shown_nodes,2);assert.equal(v.scene.edges.length,2);assert.equal(v.scene.edges[0].refs.length,2);for(const value of ['CONFIG','STATE','PRIVATE','SOURCE'])assert.ok(!JSON.stringify(v).includes(value));assert.equal(o.view({include_text:true,include_subnodes:true}).summary.counts.shown_nodes,4);assert.equal(o.view({nodes:[o.ref('c')],hops:0}).summary.nodes[0].type,'subnode');assert.equal(o.view({channels:['restricted'],include_subnodes:true}).summary.counts.shown_nodes,0);assert.equal(o.view({channels:['road'],include_subnodes:true}).summary.counts.shown_edges,2);assert.throws(()=>o.view({snapshot:'old'}),/快照/);assert.throws(()=>o.view({page:99}),/页码/);assert.deepEqual(s,fixture());});
test('node and edge aliases remain stable across filtering, edits, additions, removals and graph order',()=>{const s=fixture();s.observerIndex=indexNetwork(s.document);const o=new NetworkObserver(s,'one'),refs=o.links.map(e=>e.ref),next=structuredClone(s);next.document.network.nodes.reverse();next.document.network.nodes.find(n=>n.node_id==='a').links.unshift(edge('d'));next.document.network.nodes.push(node('aa'));next.observerIndex=indexNetwork(next.document,s.observerIndex);const n=new NetworkObserver(next,'two');assert.equal(n.ref('a'),o.ref('a'));assert.ok(Number(n.ref('aa').slice(1))>Number(o.ref('d').slice(1)));for(const e of o.links)assert.equal(n.links.find(l=>l.source===e.source&&l.target===e.target&&JSON.stringify(l.metadata)===JSON.stringify(e.metadata)).ref,e.ref);assert.equal(new Set(n.links.map(e=>e.ref)).size,n.links.length);assert.equal(n.inspectEdges({edges:[refs[0]]}).edges[0].multiplier,0);});
test('batch queries separate child mounts, preserve channel policy and limit large state',()=>{const s=fixture(),o=new NetworkObserver(s,'s');const rows=o.inspectNodes({nodes:['a','b'],section:'modules'}).nodes;assert.equal(rows[0].modules.length,1);assert.equal(rows[0].subnodes.length,1);assert.equal(rows[0].subnodes[0].ref,o.ref('c'));assert.equal(o.inspectNodes({nodes:['c'],section:'summary'}).nodes[0].parent,o.ref('a'));assert.equal(o.inspectNodes({nodes:['a'],section:'config',modules:['demo']}).nodes[0].modules.demo.private,'CONFIG');assert.equal(o.inspectModules({modules:['demo']}).modules[0].operations[0].parameters[0],'key');assert.ok(!JSON.stringify(o.inspectModules({modules:['demo']})).includes('SOURCE'));s.document.network.nodes[0].tables.modules[0].state.body='a'.repeat(9000);assert.equal(o.inspectNodes({nodes:['a'],section:'state'}).nodes[0].modules.demo.large,true);assert.throws(()=>o.inspectNodes({nodes:['missing']}),/找不到/);});
test('images are actual content blocks; text-only and render failure retain usable indices',async()=>{const o=new NetworkObserver(fixture(),'s');const result=await o.execute('view_network',{},async scene=>{assert.equal(scene.nodes.length,2);return 'cG5n';});assert.equal(result.content[1].type,'image');assert.ok(!result.content[0].text.includes('cG5n'));assert.equal((await o.execute('view_network',{image:false},()=>assert.fail())).nodes.length,2);assert.ok((await o.execute('view_network',{},()=>{throw Error('unavailable');})).image_unavailable);});

test('active text nodes remain in overview, searches find folded nodes, and invalid inputs fail clearly',()=>{const s=fixture();s.document.network.nodes.find(n=>n.node_id==='d').tables.modules.push({module_id:'clock'});s.resources.clock={release:{manifest:{signals:{config:'channels'}}}};const o=new NetworkObserver(s,'s');assert.equal(o.view().summary.nodes.some(n=>n.name==='d'),true);assert.equal(o.view({query:'c'}).summary.nodes.some(n=>n.type==='subnode'),true);assert.throws(()=>o.view('string'),/JSON 对象/);assert.throws(()=>o.view({nodes:'N1'}),/字符串列表/);});

test('edge-only selection focuses both endpoints and marks actual edges',()=>{const s=fixture();s.selection={nodes:[],edges:['a|0']};const v=new NetworkObserver(s,'s').view({selected:true,hops:0});assert.equal(v.summary.nodes.length,2);assert.ok(v.scene.edges.some(e=>e.selected));});

test('image overview contains all matching nodes, short index is explicit, details retain the same snapshot',async()=>{
 const s=fixture();s.document.network.nodes=Array.from({length:50},(_,i)=>node('item-'+i));const o=new NetworkObserver(s,'s');
 const v=o.view();assert.equal(v.scene.nodes.length,50);assert.equal(v.summary.nodes.length,24);assert.equal(v.summary.index_omitted,26);assert.equal(v.summary.pages,1);
 assert.equal(o.view({image:false}).scene.nodes.length,24);assert.equal(o.view({page_size:10,page:3}).scene.nodes.length,10);
 o.remember('V1234567890abcdef',{});
 const detail=await o.execute('view_network',{view:'V1234567890abcdef',region:'R2',show_edge_ids:true},async request=>{assert.equal(request.snapshot,'s');assert.equal(request.region,'R2');assert.equal(request.showEdgeIds,true);return {image:'cG5n',kind:'detail',visible_nodes:['N1','N2']};});
 const index=JSON.parse(detail.content[0].text);assert.equal(index.nodes.length,2);assert.equal(index.kind,'detail');
 await assert.rejects(o.execute('view_network',{view:'V1234567890abcdef',region:'R2',channels:['road']},()=>assert.fail()),/原概览/);
 await assert.rejects(o.execute('view_network',{region:'R2'},()=>assert.fail()),/概览/);
});

test('display exclusions and road relations compose, explicit hide covers active text',()=>{
 const s=fixture();s.document.network.nodes[0].links[0].attributes.relation='road';
 s.document.network.nodes.find(n=>n.node_id==='d').execution={executor:'demo'};const o=new NetworkObserver(s,'s');
 assert.ok(o.view().scene.nodes.some(n=>n.id==='d'));assert.ok(!o.view({include_text:false}).scene.nodes.some(n=>n.id==='d'));
 assert.deepEqual(o.view({exclude_types:['agent'],include_text:false}).scene.nodes.map(n=>n.id),['b']);
 const road=o.view({relations:['road']});assert.equal(road.scene.edges.length,1);assert.deepEqual(road.scene.nodes.map(n=>n.id),['a','b']);
 assert.equal(o.view({relations:['road'],exclude_nodes:['b']}).scene.edges.length,0);
 assert.equal(o.view({exclude_modules:['demo']}).scene.nodes.length,0);
 assert.deepEqual(o.view({nodes:['b'],hops:1,direction:'out'}).scene.nodes.map(n=>n.id),['b']);
 assert.deepEqual(o.inspectEdges({nodes:['b'],direction:'out'}).edges,[]);
 assert.equal(o.inspectEdges({nodes:['b'],direction:'in',relations:['road']}).edges.length,1);
 assert.equal(o.inspectEdges({relations:['road']}).edges.length,1);
 assert.equal(o.inspectEdges({channels:['info']}).edges.length,2);
 const selected=o.inspectNodes({nodes:['a'],section:'state',fields:['demo']}).nodes[0].modules.demo;
 assert.deepEqual(selected.missing_fields,['demo']);assert.deepEqual(selected.available_fields,['private']);assert.deepEqual(selected.selected,{});
});

test('views support incremental filters, clear/reset, pagination reset and scoped expiry',async()=>{
 const pool=new Map(),o=new NetworkObserver(fixture(),'s',pool),noRender=()=>assert.fail();
 const first=await o.execute('view_network',{image:false,channels:['road'],page_size:1,page:2},noRender);
 const second=await new NetworkObserver(fixture(),'s',pool).execute('view_network',{view:first.view,image:false,exclude_types:['agent']},noRender);
 assert.equal(second.page,1);assert.equal(second.nodes.length,1);assert.equal(second.nodes[0].name,'b');assert.deepEqual(second.filters.channels,['road']);
 const third=await o.execute('view_network',{view:second.view,image:false,reset:['channels'],exclude_types:[]},noRender);
 assert.equal(third.counts.shown_nodes,2);assert.equal(third.filters.channels,undefined);
 await assert.rejects(new NetworkObserver(fixture(),'other',pool).execute('view_network',{view:first.view,image:false},noRender),/快照/);
 await assert.rejects(new NetworkObserver(fixture(),'s').execute('view_network',{view:first.view,image:false},noRender),/失效/);
 await assert.rejects(o.execute('view_network',{view:first.view,reset:['source'],image:false},noRender),/不能重置/);
 for(let i=0;i<30;i++)await o.execute('view_network',{query:String(i),image:false},noRender);assert.equal(pool.size,24);
 await assert.rejects(o.execute('view_network',{view:first.view,image:false},noRender),/失效/);
});
