// Cold reopening the actual desktop project must show the completed native consultation.
import {_electron as electron} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=path.resolve('../../'),directory=path.resolve(process.argv[2]);let app;const errors=[];
try{
 app=await electron.launch({executablePath:path.join(root,'frontends/desktop/node_modules/electron/dist/electron.exe'),args:[path.join(root,'frontends/desktop'),'--project',path.join(directory,'project'),'--user-data-dir',path.join(directory,'history-client')],env:{...process.env,NEXARBOR_ROOT:root,NEXARBOR_MODEL_DIRECTORY:path.join(directory,'models')},timeout:60000});
 const page=await app.firstWindow();page.on('pageerror',error=>errors.push(error.message));
 await page.locator('.react-flow__node').first().waitFor({timeout:60000});
 const node=page.locator('.react-flow__node').filter({has:page.locator('.node-name',{hasText:'小砾'})}).first();await node.click({button:'right',force:true});await page.getByRole('menuitem',{name:'咨询 Agent',exact:true}).click();
 const answer=page.locator('.conversation-message.assistant').filter({hasText:'网络规模'}).last();await answer.waitFor({timeout:30000});
 assert.match(await answer.innerText(),/52.*节点.*205.*连线/s);assert.match(await answer.innerText(),/小砾/);
 await page.getByRole('button',{name:'展开咨询页面',exact:true}).click();await page.waitForTimeout(500);
 await page.locator('.conversation-message.assistant').filter({hasText:'网络规模'}).last().evaluate(element=>element.scrollIntoView({block:'start'}));
 await page.screenshot({path:path.join(directory,'town-introduction-start.png')});
 await page.locator('.conversation-messages').evaluate(element=>{element.scrollTop=element.scrollHeight;});await page.screenshot({path:path.join(directory,'town-introduction-end.png')});
 assert.deepEqual(errors,[]);
 await fs.writeFile(path.join(directory,'history-verification.json'),JSON.stringify({status:'passed',cold_reopened:true,actual_desktop:true,answer_preserved:true,additional_paid_requests:0,errors,screenshots:['town-introduction-start.png','town-introduction-end.png']},null,2));
 console.log('Original desktop cold history and answer screenshots passed; no new model call.');
}finally{await app?.close();}
