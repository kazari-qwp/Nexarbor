import test from 'node:test';import assert from 'node:assert/strict';import {moduleTable} from '../../shared/graph/node-records.js';
import {mergeDataEdit} from '../src/data-edit.js';
test('data replies preserve unrelated edits and refuse changed target configuration or owned files',()=>{
 const node={node_id:'one',data:{path:'data/one',directory:true,save_data:true},tables:{modules:[]}},before={network:{nodes:[node,{node_id:'two',tables:{modules:[]},links:[]}]},files:{'data/one/page.md':'old','other.md':'before'}},value={beforeNode:structuredClone(node),beforeFiles:structuredClone(before.files),node:structuredClone(node),files:{'data/one/page.md':'new'}};
 const current=structuredClone(before);current.network.nodes[1].name='keep edit';current.files['other.md']='keep text';const result=mergeDataEdit(current,value);assert.equal(result.network.nodes[1].name,'keep edit');assert.equal(result.files['other.md'],'keep text');assert.equal(result.files['data/one/page.md'],'new');assert.equal(before.files['data/one/page.md'],'old');
 current.files['data/one/new.md']='concurrent addition';assert.throws(()=>mergeDataEdit(current,value),/数据已经变化/);delete current.files['data/one/new.md'];current.network.nodes[0].name='changed';assert.throws(()=>mergeDataEdit(current,value),/配置已经变化/);
});

import {mergeClearedData,isDataNode} from '../src/data-edit.js';
test('clear replaces only owned storage and data while retaining unrelated draft configuration',()=>{
 const n={type:'knowledge_collection',node_id:'one',name:'before',data:{path:'data/one',directory:true,save_data:true,parameters:{storage:'wiki'}},tables:{modules:[{module_id:'data.local',config:{read_only:true}}]}},doc={network:{nodes:[structuredClone(n)]},files:{'data/one/page.md':'erase','data/one/history/v1':'erase too','other.md':'keep'}};
 doc.network.nodes[0].name='pending name';doc.network.nodes[0].links=[{target_id:'two',channels:['a'],threshold:0,processor:{type:'multiplier',factor:1}}];
 const result=mergeClearedData(doc,{beforeNode:n,node:n,roots:[['data/one','directory']],files:{'data/one/catalog.sqlite3':{encoding:'base64',data:'AA=='}}});
 assert.equal(result.network.nodes[0].name,'pending name');assert.deepEqual(result.network.nodes[0].links,doc.network.nodes[0].links);assert.equal(result.files['other.md'],'keep');assert.equal(result.files['data/one/page.md'],undefined);assert.equal(result.files['data/one/history/v1'],undefined);assert.equal(moduleTable(result.network.nodes[0])['data.local'].config.read_only,true);
 doc.network.nodes[0].data.path='data/another';assert.throws(()=>mergeClearedData(doc,{beforeNode:n,node:n,roots:[],files:{}}),/存储位置/);
 for(const type of ['markdown','value','csv','sqlite','knowledge_collection','llamaindex'])assert.equal(isDataNode({type,data:{path:'data/file',directory:false,save_data:true}}),true);assert.equal(isDataNode({type:'node',tables:{modules:[{module_id:'knowledge.collection',config:{}}]}}),true);assert.equal(isDataNode({type:'agent'}),false);
});
