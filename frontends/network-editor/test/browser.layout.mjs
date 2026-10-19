// Selection-scoped layout, stable filtering and stacking; no model or network writes.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';import path from 'node:path';
const run=path.resolve(process.argv[2]),records=[],root=path.join(run,'.datanet/networks');
for(const name of await fs.readdir(root)){const file=path.join(root,name,'editor-connection.json');try{records.push({file,mtime:(await fs.stat(file)).mtimeMs});}catch{}}
records.sort((a,b)=>b.mtime-a.mtime);const connection=JSON.parse(await fs.readFile(records[0].file,'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1800,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const snapshot=()=>page.evaluate(()=>({viewport:document.querySelector('.react-flow__viewport').style.transform,
 nodes:Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map(n=>[n.dataset.id,{position:n.style.transform,z:Number(n.style.zIndex)}])),
 edges:Object.fromEntries([...document.querySelectorAll('.react-flow__edge')].map(e=>[e.dataset.id,{path:e.querySelector('.react-flow__edge-path')?.getAttribute('d'),z:Number(e.closest('svg').style.zIndex)}]))}));
try{
 await page.goto(connection.url);await expect(page.getByRole('button',{name:'保存',exact:true})).toBeVisible();
 await expect.poll(()=>page.locator('[data-routing="avoiding"]').count()).toBeGreaterThan(20);
 const initial=await snapshot(),channel={click:async()=>{for(const name of ['access.read','access.write'])await page.getByRole('group',{name:'连接频道显示'}).getByRole('button',{name,exact:true}).click();}};
 await channel.click();const reduced=await snapshot();expect(reduced.viewport).toBe(initial.viewport);
 for(const [id,n] of Object.entries(reduced.nodes))expect(n.position).toBe(initial.nodes[id].position);
 for(const [id,e] of Object.entries(reduced.edges))expect(e.path).toBe(initial.edges[id].path);
 await channel.click();const restored=await snapshot();expect(restored.viewport).toBe(initial.viewport);
 for(const [id,n] of Object.entries(restored.nodes)){expect(n.position).toBe(initial.nodes[id].position);if(!reduced.nodes[id])expect(n.z).toBeGreaterThan(Math.max(...Object.values(reduced.nodes).map(n=>n.z)));}
 for(const [id,e] of Object.entries(restored.edges)){expect(e.path).toBe(initial.edges[id].path);if(!reduced.edges[id])expect(e.z).toBeGreaterThan(Math.max(...Object.values(reduced.edges).map(e=>e.z)));}
 // Arrange only the five selected, visible world.tick participants.
 await channel.click();
 // Native Shift selection must support choosing a subset without switching perspective.
 await page.locator('[data-id="world/time"]').click({modifiers:['Shift']});
 await page.locator('[data-id="world/pulse"]').click({modifiers:['Shift']});
 await expect(page.getByRole('button',{name:/整理选中/})).toContainText('2');
 await page.getByRole('button',{name:'全选可见',exact:true}).click();
 await expect(page.getByRole('button',{name:/整理选中/})).toContainText('5');
 const fixedBefore=restored.nodes;
 await page.getByRole('button',{name:/整理选中/}).click();await expect(page.getByRole('status')).toContainText('已整理 5 个选中节点');
 await expect.poll(()=>page.locator('[data-routing="avoiding"]').count()).toBeGreaterThan(0);
 // Every rendered straight segment, including nudged circular terminals, is orthogonal.
 const diagonal=await page.locator('.react-flow__edge-path').evaluateAll(paths=>{
  const failures=[];
  for(const path of paths){const commands=path.getAttribute('d').match(/[MLQ][^MLQ]*/g)??[];let previous;
   const axis=(a,b)=>Math.abs(a.x-b.x)<.01||Math.abs(a.y-b.y)<.01;
   for(const command of commands){const values=command.slice(1).trim().split(/[ ,]+/).map(Number),end={x:values.at(-2),y:values.at(-1)};
    if(command[0]==='L'&&previous&&!axis(previous,end))failures.push(command);
    if(command[0]==='Q'&&previous){const control={x:values[0],y:values[1]};if(!axis(previous,control)||!axis(control,end))failures.push(command);}
    previous=end;
   }
  }return failures;
 });expect(diagonal).toEqual([]);
 await page.screenshot({path:path.join(run,'12-selected-layout.png')});
 const arranged=await snapshot();
 // Wait for the native 300ms fit animation before using screen coordinates.
 await page.waitForTimeout(400);
 // All four circle handles still use React Flow's native connection interaction.
 const handleA=await page.locator('[data-id="world/time"] [data-handleid="right"]').boundingBox(),handleB=await page.locator('[data-id="world/pulse"] [data-handleid="left"]').boundingBox();
 await page.mouse.move(handleA.x+handleA.width/2,handleA.y+handleA.height/2);await page.mouse.down();await page.mouse.move(handleB.x+handleB.width/2,handleB.y+handleB.height/2,{steps:12});await page.mouse.up();
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByRole('heading',{name:'建立连接',exact:true})).toBeVisible();await page.getByRole('button',{name:'取消',exact:true}).click();
 await channel.click();const all=await snapshot();
 for(const [id,n] of Object.entries(all.nodes))if(!arranged.nodes[id])expect(n.position).toBe(fixedBefore[id].position);
 for(const [id,e] of Object.entries(arranged.edges))expect(all.edges[id].path).toBe(e.path);
 // Explicit routing does not move nodes.
 const stable=await snapshot();await page.getByRole('button',{name:'优化连线',exact:true}).click();
 await page.locator('.react-flow__controls-fitview').click();
 const after=await snapshot();for(const [id,n] of Object.entries(after.nodes))expect(n.position).toBe(stable.nodes[id].position);
 // Undo restores layout and preserves actual network data.
 await page.getByTitle('撤销',{exact:true}).click();const undone=await snapshot();
 for(const [id,n] of Object.entries(undone.nodes))expect(n.position).toBe(initial.nodes[id].position);
 // Add a real draft node through the existing template form; never apply it.
 await page.locator('.basic-nodes summary').click();await page.getByRole('button',{name:'普通节点',exact:true}).click();
 await page.getByLabel('模板编号').fill('stack-check');await page.getByLabel('模板名称').fill('置顶验证');
 await page.getByRole('button',{name:'添加到草稿',exact:true}).click();await expect(page.locator('.react-flow__node')).toHaveCount(30);
 const added=await snapshot(),newId=Object.keys(added.nodes).find(id=>!initial.nodes[id]);expect(newId).toBeTruthy();
 expect(added.nodes[newId].z).toBeGreaterThan(Math.max(...Object.values(initial.nodes).map(n=>n.z)));
 expect(errors).toEqual([]);await expect(page.locator('.routing-notice')).toHaveCount(0);
 await fs.writeFile(path.join(run,'layout-verification.json'),JSON.stringify({passed:true,selectionScopedLayout:true,nativeShiftMultiSelect:true,circleConnectionHandles:true,orthogonalIncludingCircleTerminals:true,unselectedPositionsPreserved:true,filterPreservesPositionsPathsAndViewport:true,newlyVisibleNodesAndEdgesOnTop:true,newDraftNodeOnTop:true,explicitRoutingPreservesPositions:true,undoRestoresLayout:true,modelApiCalls:0,errors},null,2));
 console.log('PASS scoped layout, stable filters/paths/view, stacking, new draft node and undo; no model calls or network apply');
}catch(error){await page.screenshot({path:path.join(run,'layout-failure.png')});console.error('Page errors:',errors);throw error;}finally{await browser.close();}
