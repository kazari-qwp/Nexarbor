// Real desktop run controls and original clock counter; no Agent activation or model calls.
import {_electron,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';
import {editorNode} from '../../../adapt/harness/framework/editor-nodes.js';
import {setModule} from '../../shared/graph/node-records.js';import {linkRecord} from '../../shared/graph/links.js';
import {copyProjectLibrary} from './support/project-library.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),directory=await fs.mkdtemp(path.join(root,'build/pulse-controls-client-'));
await copyProjectLibrary(path.join(root,'项目演示/应用3-NPC小镇-初始'),directory);
let host=await startStudio({directory}),client,page;const errors=[],apiErrors=[];
const launch=async()=>{const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--connection',path.join(directory,'editor-connection.json'),'--user-data-dir',path.join(directory,'client')],env});page=await client.firstWindow();page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400&&r.url().endsWith('/api'))apiErrors.push(r.status());});await expect(page.getByLabel('执行脉冲')).toBeVisible({timeout:30000});};
const tick=async()=>(await host.request('module.call',{node:'counter',module:'clock.counter',operation:'read',arguments:{}})).tick;
try{
 const initial=await host.request('state',{}),document=initial.live.document;
 const pulse=editorNode('pulse','test-pulse','验收脉冲'),counter=editorNode('node','counter','原时钟计数器');
 pulse.parameters={channels:['tick'],strength:2};pulse.links=[linkRecord('counter',{channels:['tick'],threshold:0,multiplier:1})];counter.links=[linkRecord('test-pulse',{channels:['tick'],threshold:0,multiplier:1})];
 setModule(counter,'clock.counter',{config:{signal_channels:['tick'],initial_tick:0,checkpoint_every:0,write_text:false},state:{},channels:[],strength:0});
 document.network.nodes.push(pulse,counter);await host.request('apply',{document,base_commit:initial.live.commit,layout:{root:{x:0,y:0},'test-pulse':{x:0,y:180},counter:{x:220,y:180}}});
 await launch();await page.getByLabel('执行脉冲').selectOption('test-pulse');await page.getByRole('button',{name:'单步',exact:true}).click();await expect.poll(tick,{timeout:15000}).toBe(1);await expect(page.getByRole('button',{name:'运行',exact:true})).toBeEnabled();
 await page.getByLabel('运行时刻数').fill('3');await page.getByRole('button',{name:'运行',exact:true}).click();await expect.poll(tick,{timeout:15000}).toBe(4);await expect(page.getByRole('button',{name:'运行',exact:true})).toBeEnabled();
 await page.screenshot({path:path.join(directory,'pulse-controls.png')});await page.evaluate(()=>window.nexarborWorkspace.flush());await client.close();client=null;await host.close();host=await startStudio({directory});await launch();expect(await tick()).toBe(4);await expect(page.getByLabel('执行脉冲')).toHaveValue('test-pulse');await expect(page.getByLabel('运行时刻数')).toHaveValue('5');expect(errors).toEqual([]);expect(apiErrors).toEqual([]);
 await fs.writeFile(path.join(directory,'verification.json'),JSON.stringify({passed:true,singleStep:1,continuousSteps:3,finalTick:4,realSignalRuntime:true,coldReopen:true,modelCalls:0,errors,apiErrors},null,2));console.log('PASS '+directory);
}catch(error){await page?.screenshot({path:path.join(directory,'failure.png')}).catch(()=>{});throw error;}finally{await client?.close();await host.close();}
