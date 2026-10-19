// 用原生客户端查看真实日志中的工具图片，不发送消息、不调用模型。
import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';import {_electron,expect} from '@playwright/test';
const root=fileURLToPath(new URL('../../../',import.meta.url)),fixture=path.resolve(process.argv[2]),base=path.join(root,'build/scene-browser-'+Date.now());await fs.mkdir(base,{recursive:true});
const env={...process.env,DATANET_HARNESS_CREDENTIALS:path.join(fixture,'fake-grant.yaml')};delete env.ELECTRON_RUN_AS_NODE;
const client=await _electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',path.join(fixture,'clone'),'--user-data-dir='+path.join(base,'profile')],env});let page;
try{
 page=await client.firstWindow();await expect(page.locator('.react-flow__node[data-id="a"]')).toBeVisible({timeout:30000});await page.locator('.react-flow__node[data-id="a"]').dblclick();
 const dialog=page.locator('.chat-dialog');await expect(dialog).toBeVisible();const image=dialog.locator('.chat-image img');await expect(image).toBeVisible({timeout:20000});
 expect(await image.evaluate(img=>img.complete&&img.naturalWidth>=1000)).toBe(true);await page.screenshot({path:path.join(base,'map-in-chat.png')});await fs.writeFile(path.join(base,'verification.json'),JSON.stringify({passed:true,nativeToolImageVisible:true,paidCalls:0},null,2));console.log('PASS '+base);
}catch(error){if(page&&!page.isClosed())await page.screenshot({path:path.join(base,'failure.png')});throw error;}finally{await client.close();}
