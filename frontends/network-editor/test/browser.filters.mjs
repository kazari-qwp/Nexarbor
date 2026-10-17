// Display-only acceptance against the existing workbench; never runs Agents.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const run=path.resolve(process.argv[2]),roots=path.join(run,'.datanet/networks'),records=[];
for(const folder of await fs.readdir(roots)){const file=path.join(roots,folder,'editor-connection.json');try{records.push({file,mtime:(await fs.stat(file)).mtimeMs});}catch{}}
records.sort((a,b)=>b.mtime-a.mtime);const connection=JSON.parse(await fs.readFile(records[0].file,'utf8'));
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(connection.url);await expect(page.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 const kinds=page.getByRole('group',{name:'节点类型显示'}).getByRole('button');
 const channels=page.getByRole('group',{name:'连接频道显示'}).getByRole('button');
 const nodes=page.locator('.react-flow__node'),edges=page.locator('.react-flow__edge');
 await expect(kinds.first()).toHaveAttribute('aria-pressed','true');
 const total=await nodes.count();expect(total).toBeGreaterThan(0);
 for(const button of [...await kinds.all(),...await channels.all()])await expect(button).toHaveAttribute('aria-pressed','true');
 await page.getByRole('group',{name:'节点类型显示'}).getByRole('button',{name:'文本',exact:true}).click();
 await expect.poll(()=>nodes.count()).toBeLessThan(total);expect(await nodes.count()).toBeGreaterThan(0);
 for(const button of await kinds.all())if(await button.getAttribute('aria-pressed')==='true')await button.click();
 await expect(nodes).toHaveCount(0);await expect(edges).toHaveCount(0);
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();await expect(nodes).toHaveCount(total);
 for(const button of await channels.all())await button.click();
 await expect(nodes).toHaveCount(0);await expect(edges).toHaveCount(0);
 await page.getByRole('group',{name:'连接频道显示'}).getByRole('button',{name:'普通连接',exact:true}).click();
 await expect.poll(()=>edges.count()).toBeGreaterThan(0);await expect(page.locator('.react-flow__edge-text')).not.toContainText(['world.tick']);
 await page.getByRole('button',{name:'清除筛选',exact:true}).click();await expect(nodes).toHaveCount(total);
 for(const button of [...await kinds.all(),...await channels.all()])await expect(button).toHaveAttribute('aria-pressed','true');
 await page.screenshot({path:path.join(run,'09-display-switches.png')});expect(errors).toEqual([]);
 await fs.writeFile(path.join(run,'filter-verification.json'),JSON.stringify({passed:true,defaultAllEnabled:true,hideOneCategoryInOneClick:true,noNodeTypesShowsNothing:true,noChannelsShowsNothing:true,ordinaryConnectionsSelectable:true,clearRestoresAll:true,modelApiCalls:0,errors},null,2));
 console.log('PASS default-all, one-click hide, all-off empty, ordinary links and reset; no model calls');
}finally{await browser.close();}
