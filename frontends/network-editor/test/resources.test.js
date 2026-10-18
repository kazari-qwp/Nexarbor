import test from 'node:test';import assert from 'node:assert/strict';
import {resource,attachResource,attachResources,folderResources,resources,assetHistory,matchesType,resourceTitle} from '../src/resources.js';
import {historyBookmark} from '../src/subnets.js';
const catalog={modules:{'example.x':{label:'示例',description:'局部组件',node_types:['node'],defaults:{config:{value:1},state:{count:0},access:{strength:2,channels:['x']}}}},tools:[{ref:'harness:Read',name:'Read',description:'读取文件'}]};
const document={network:{nodes:[{node_id:'a',type:'node',modules:{},offered_tools:[]},{node_id:'b',type:'agent',modules:{},offered_tools:[]}]},files:{}};
test('standalone presets isolate config; attachment preserves module runtime state and unrelated nodes',()=>{
 const preset=resource(catalog,'module','example.x');preset.asset.config.value=5;
 assert.equal(catalog.modules['example.x'].defaults.config.value,1);
 const next=attachResource(document,'a',preset.asset,catalog);assert.equal(document.network.nodes[0].modules['example.x'],undefined);
 assert.deepEqual(next.network.nodes[1],document.network.nodes[1]);next.network.nodes[0].modules['example.x'].state.count=9;
 assert.equal(attachResource(next,'a',preset.asset,catalog).network.nodes[0].modules['example.x'].state.count,9);
 assert.throws(()=>attachResource(next,'b',preset.asset,catalog),/节点类型/);assert.throws(()=>attachResource(next,'missing',preset.asset,catalog),/拖到节点/);
});
test('batch attachment is all-or-nothing to its caller and archive hides resources without removing configuration',()=>{
 const module=resource(catalog,'module','example.x'),tool=resource(catalog,'tool','harness:Read');
 assert.throws(()=>attachResources(document,'b',[tool.asset,module.asset],catalog),/节点类型/);assert.deepEqual(document.network.nodes[1].offered_tools,[]);
 const next=attachResources(document,'a',[tool.asset,module.asset],catalog);assert.equal(next.network.nodes[0].offered_tools.length,1);assert.ok(next.network.nodes[0].modules['example.x']);
 const org={module:{items:{'example.x':{archivedAt:1}}}};assert.deepEqual(resources(catalog,'module',org),[]);assert.equal(resources(catalog,'module',org,true).length,1);assert.throws(()=>attachResource(document,'a',module.asset,catalog,org),/归档或删除/);
 const tree={folders:[{id:'a',parent:null},{id:'b',parent:'a'}],items:{'example.x':{folder:'b'}}};assert.deepEqual(folderResources(tree,[module],'a'),[module]);
});
test('tool presets deduplicate references and resource history keeps the configuration without graph snapshots',()=>{
 const preset=resource(catalog,'tool','harness:Read',{tool:{items:{'harness:Read':{name:'阅读'}}}});
 assert.equal(preset.name,'阅读');assert.equal(resourceTitle(preset),'阅读：读取文件');
 const first=attachResource(document,'a',preset.asset,catalog);preset.asset.channels=['public'];
 const second=attachResource(first,'a',preset.asset,catalog);assert.equal(second.network.nodes[0].offered_tools.length,1);assert.deepEqual(second.network.nodes[0].offered_tools[0].channels,['public']);
 const entry=assetHistory(preset),copy=historyBookmark(entry);assert.equal(copy.kind,'tool');assert.deepEqual(copy.asset,preset.asset);assert.equal(copy.snapshot,undefined);
 assert.equal(matchesType(copy,'tool'),true);assert.equal(matchesType(copy,'node'),false);assert.equal(matchesType({mode:'internal',snapshot:{nodes:[{},{}]}},'network'),true);
});
