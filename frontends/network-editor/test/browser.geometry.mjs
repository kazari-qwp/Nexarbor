// Real canvas geometry and pointer interactions; no Agent execution or saves.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const run=path.resolve(process.argv[2]),records=[],root=path.join(run,'.datanet/networks');
for(const name of await fs.readdir(root)){const file=path.join(root,name,'editor-connection.json');try{records.push({file,mtime:(await fs.stat(file)).mtimeMs});}catch{}}
records.sort((a,b)=>b.mtime-a.mtime);const connection=JSON.parse(await fs.readFile(records[0].file,'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(connection.url);await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 await page.getByRole('group',{name:'连接频道显示'}).getByRole('button',{name:'普通连接',exact:true}).click();
 await page.locator('.react-flow__controls-fitview').click();
 const npc=page.locator('.react-flow__node[data-id="world/npc/alice"]'),time=page.locator('.react-flow__node[data-id="world/time"]');
 const before=await npc.boundingBox();expect(before.width).toBeCloseTo(before.height,0);
 await expect(npc.locator('.network-node')).toHaveCSS('border-radius','50%');
 await expect(npc.locator('.node-details')).toHaveCSS('visibility','hidden');
 await npc.hover();await expect(npc.locator('.node-details')).toHaveCSS('opacity','1');
 const card=await npc.locator('.node-details').boundingBox();expect(card.width).toBeGreaterThan(before.width);
 expect(Math.abs(card.x+card.width/2-before.x-before.width/2)).toBeLessThan(2);
 await page.screenshot({path:path.join(run,'10-node-hover.png')});
 const destination=await time.boundingBox();const x=destination.x+destination.width/2,y=Math.max(220,destination.y-260);
 const wire=page.locator('.react-flow__edge[aria-label^="world/time → world/npc/alice"] [data-source-side]');
 await page.mouse.move(before.x+before.width/2,before.y+before.height/2);await page.mouse.down();await page.mouse.move(x,y,{steps:12});
 const during=await npc.boundingBox();expect(Math.hypot(during.x-before.x,during.y-before.y)).toBeGreaterThan(40);
 await expect(wire).toHaveAttribute('data-source-side','top');await page.mouse.up();
 await page.locator('.react-flow__pane').click({position:{x:12,y:16}});await expect(npc.locator('.node-details')).toHaveCSS('visibility','hidden');
 await expect(page.locator('.react-flow__edge-text')).toHaveCount(0);
 // Move an unrelated node into this wire: the reused router must reroute it.
 const midpoint=await wire.locator('.react-flow__edge-path').evaluate(p=>{const q=p.getPointAtLength(p.getTotalLength()/2),s=new DOMPoint(q.x,q.y).matrixTransform(p.getScreenCTM());return {x:s.x,y:s.y};});
 const obstacle=page.locator('.react-flow__node[data-id="world/savepoint"]'),ob=await obstacle.boundingBox();
 await page.mouse.move(ob.x+ob.width/2,ob.y+ob.height/2);await page.mouse.down();await page.mouse.move(midpoint.x,midpoint.y,{steps:12});await page.mouse.up();await page.mouse.move(270,135);
 // Let the worker settle, then sample rendered SVG paths against unrelated circles.
 await expect.poll(async()=>page.locator('[data-routing="avoiding"]').count()).toBeGreaterThan(0);
 const collisions=await page.locator('.react-flow__edge').evaluateAll(elements=>{
  const boxes=[...document.querySelectorAll('.react-flow__node')].map(n=>({id:n.dataset.id,box:n.getBoundingClientRect()})),hits=[];
  for(const edge of elements){const label=edge.getAttribute('aria-label')??'',p=edge.querySelector('.react-flow__edge-path');if(!p)continue;
   const total=p.getTotalLength(),matrix=p.getScreenCTM();
   for(let at=0;at<=total;at+=4){const q=p.getPointAtLength(at),point=new DOMPoint(q.x,q.y).matrixTransform(matrix);
    for(const n of boxes){if(label.startsWith(n.id+' → ')||label.includes(' → '+n.id+' · '))continue;
     const b=n.box,cx=b.x+b.width/2,cy=b.y+b.height/2,r=b.width/2-3;
     if((point.x-cx)**2+(point.y-cy)**2<r*r){hits.push({edge:label,node:n.id});break;}
    }if(hits.length>10)return hits;
   }
  }return hits;
 });expect(collisions).toEqual([]);
 await page.screenshot({path:path.join(run,'11-rounded-routing.png')});expect(errors).toEqual([]);
 await fs.writeFile(path.join(run,'geometry-verification.json'),JSON.stringify({passed:true,circularNodes:true,hoverExpandsAroundSameCenter:true,positionUpdatesBeforePointerUp:true,portsFollowDraggedPosition:true,labelsHiddenByDefault:true,renderedPathsAvoidUnrelatedNodes:true,modelApiCalls:0,errors},null,2));
 console.log('PASS circles, hover expansion, native continuous drag, port changes and obstacle-free rendered paths; no model calls');
}catch(error){await page.screenshot({path:path.join(run,'geometry-failure.png')});console.error('Page errors:',errors);throw error;}finally{await browser.close();}
