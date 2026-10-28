import {fileURLToPath} from 'node:url';
import {moduleTable,nodeSkills,offeredPorts} from '../../shared/graph/node-records.js';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
import {resource,attachResources,resourceRelations,matchesType,assetHistory,resources} from '../src/resources.js';
import {historyBookmark} from '../src/subnets.js';
import {editorLibrary} from '../../../adapt/harness/framework/editor-library.js';
const defaults={config:{value:1},state:{count:0},access:{strength:1,channels:['records']}};
const catalog={modules:{base:{label:'基础',defaults},feature:{label:'功能',requires:['base'],defaults}},tools:[{ref:'module:feature/read',module:'feature',requires:['feature'],name:'读取'},{ref:'host:read',name:'宿主读取'}],skills:{basic:{name:'基本',requires:['base'],tools:[],skills:[],local:true},advanced:{name:'高级',requires:['feature'],tools:['module:feature/read','host:read'],skills:['basic'],local:true}}};
const doc={network:{nodes:[{node_id:'a',type:'agent',tables:{modules:[{module_id:'base',config:{value:9},state:{count:12},strength:2,channels:['custom']}]},links:[]},{node_id:'b',type:'agent',tables:{modules:[]},links:[]},{node_id:'n',type:'node',tables:{modules:[]},links:[]}]},files:{}};
test('recursive Skill assembly preserves existing components, deduplicates, stays local and rejects incomplete cycles atomically',()=>{
 const value=resource(catalog,'skill','advanced'),next=attachResources(doc,'a',[value.asset,value.asset],catalog),a=next.network.nodes[0];
 assert.deepEqual(nodeSkills(a),['basic','advanced']);assert.deepEqual(Object.keys(moduleTable(a)).sort(),['base','feature']);assert.deepEqual(moduleTable(a).base,moduleTable(doc.network.nodes[0]).base);assert.equal(offeredPorts(a,next.network.properties).length,1);assert.equal(offeredPorts(a,next.network.properties)[0].ref,'host:read');assert.equal(next.network.nodes[1].execution?.skills,undefined);assert.equal(doc.network.nodes[0].execution?.skills,undefined);
 assert.deepEqual(resourceRelations(value,catalog),{modules:['feature'],tools:['module:feature/read','host:read'],skills:['basic']});
 assert.equal(matchesType(historyBookmark(assetHistory(value)),'skill'),true);assert.equal(resources(catalog,'skill').length,2);
 assert.throws(()=>attachResources(doc,'n',[value.asset],catalog),/Agent/);
 const bad=structuredClone(catalog);bad.skills.basic.skills=['advanced'];assert.throws(()=>attachResources(doc,'b',[value.asset],bad),/成环/);assert.deepEqual(moduleTable(doc.network.nodes[1]),{});
 delete bad.skills.basic.skills;bad.skills.advanced.tools=['missing'];assert.throws(()=>attachResources(doc,'b',[value.asset],bad),/缺少依赖/);assert.equal(doc.network.nodes[1].execution?.skills,undefined);
});
test('Skills use persistent bookmarks, MRU history and virtual folders with archive/restore',async()=>{
 const folder=await fs.mkdtemp(path.resolve(fileURLToPath(new URL('../../../build/',import.meta.url)),'skills-library-')),library=editorLibrary(folder,{catalog:async()=>catalog}),change=p=>library('editor.library.update',p);
 const advanced=resource(catalog,'skill','advanced'),basic=resource(catalog,'skill','basic'),book={id:'bookmark',kind:'skill',name:'技能书签',asset:advanced.asset,category:'default',createdAt:1};
 await change({action:'bookmark.patch',changes:[{id:book.id,expected:null,value:book}]});
 for(const value of [advanced,basic,advanced])await change({action:'history.push',entries:[assetHistory(value)]});
 await change({action:'asset.folder.create',kind:'skill',id:'folder',name:'我的技能'});await change({action:'asset.move',kind:'skill',entry:{type:'item',id:'advanced'},target:'folder'});await change({action:'asset.archive',kind:'skill',entries:[{id:'advanced'}]});
 let state=await editorLibrary(folder,{catalog:async()=>catalog})('editor.library');assert.deepEqual(state.history.map(h=>h.asset.id),['advanced','basic']);assert.deepEqual(state.bookmarks[0].asset,{kind:'skill',id:'advanced'});assert.equal(resources(catalog,'skill',state.assets).length,1);
 await change({action:'asset.restore',kind:'skill',entries:[{id:'advanced'}]});state=await library('editor.library');assert.equal(state.assets.skill.items.advanced.folder,'folder');assert.deepEqual(state.assets.skill.items.advanced.archivedAt,undefined);
});
