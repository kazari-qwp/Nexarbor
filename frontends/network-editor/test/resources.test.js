import test from 'node:test';import assert from 'node:assert/strict';
import {resource,attachResource,attachResources,folderResources,resources,assetHistory,matchesType,resourceTitle,nodeTools,resourceRelations,completeModules} from '../src/resources.js';
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
test('dependencies expand recursively; badges count one level and tools resolve to the same module instance',()=>{
 const defaults={config:{},state:{},access:{strength:2,channels:['movement']}};
 const c={modules:{a:{label:'甲',requires:['b'],tools:['module:a/go'],node_types:['node'],defaults},b:{label:'乙',requires:['c'],tools:[],node_types:['node'],defaults},c:{label:'丙',requires:[],tools:[],node_types:['node'],defaults}},tools:[{ref:'module:a/go',name:'移动',module:'a',requires:['a'],channels:['movement']}]};
 const preset=resource(c,'tool','module:a/go');let result=attachResource(document,'a',preset.asset,c);
 assert.deepEqual(Object.keys(result.network.nodes[0].modules).sort(),['a','b','c']);assert.equal(nodeTools(result.network.nodes[0],c).length,1);assert.deepEqual(result.network.nodes[0].offered_tools,[]);
 result.network.nodes[0].modules.b.config={custom:12};result=attachResources(result,'a',[preset.asset,resource(c,'module','a').asset,preset.asset],c);
 assert.deepEqual(result.network.nodes[0].modules.b.config,{custom:12});assert.equal(Object.keys(result.network.nodes[0].modules).length,3);assert.equal(nodeTools(result.network.nodes[0],c).length,1);
 assert.equal(resourceRelations(resource(c,'module','a'),c).modules.length,1);assert.equal(resourceRelations(preset,c).modules.length,1);
 const partial=structuredClone(document);partial.network.nodes[0].modules.a=structuredClone(defaults);assert.equal(Object.keys(completeModules(partial,c).network.nodes[0].modules).length,3);
 c.modules.c.requires=['a'];assert.throws(()=>attachResource(document,'a',preset.asset,c),/成环/);assert.deepEqual(document.network.nodes[0].modules,{});
 delete c.modules.c;assert.throws(()=>attachResource(document,'a',preset.asset,c),/缺少依赖/);
});
test('configuration-only maker bookmarks preserve existing grants and state',()=>{
 const original=structuredClone(document);original.network.nodes[0].modules['example.x']={config:{value:1},state:{count:9},access:{strength:1,channels:['narrow']}};
 const updated=attachResource(original,'a',{kind:'module',id:'example.x',config:{value:5}},catalog);
 assert.deepEqual(updated.network.nodes[0].modules['example.x'],{config:{value:5},state:{count:9},access:{strength:1,channels:['narrow']}});
 assert.equal(original.network.nodes[0].modules['example.x'].config.value,1);
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
