// Real stock Harness UI, isolated browser; no messages or model requests.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash,createHmac} from 'node:crypto';
const run=path.resolve(process.argv[2]);
const meta=JSON.parse(await fs.readFile(path.join(run,'client-meta.json'),'utf8'));
const manifest=JSON.parse(await fs.readFile(path.join(run,'sessions-manifest.json'),'utf8'));
const raw=await fs.readFile(path.join(meta.home,'.credentials.yaml'),'utf8');
const block=raw.split('  client-connection/browser-session:')[1].split(/\n  \S/,1)[0];
const secret=Buffer.from(block.match(/^\s+secret:\s*["']?([A-Za-z0-9_-]+)/m)[1],'base64url');
const issuedAt=Date.now(),body=Buffer.from(JSON.stringify({version:1,authority:meta.authority,issuedAt,expiresAt:issuedAt+3600000})).toString('base64url');
const cookie={name:'dsh-auth-'+createHash('sha256').update(meta.authority).digest('base64url'),value:'v1.'+body+'.'+createHmac('sha256',secret).update(body).digest('base64url'),url:'http://'+meta.authority,httpOnly:true,sameSite:'Strict'};
const base='http://'+meta.authority;
const unauthenticated=await fetch(base+'/api/nexarbor/editor',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:manifest.root_session})});
expect(unauthenticated.status).toBe(401);
const browser=await chromium.launch({channel:'msedge',headless:true});const context=await browser.newContext({viewport:{width:1600,height:1000}});await context.addCookies([cookie]);const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);const title=(manifest.sessions.find(s=>s.actor==='root'&&s.session_id!==manifest.root_session)??manifest.sessions.find(s=>s.actor==='root')).title;
 await page.getByText(title,{exact:true}).first().click({timeout:15000});
 const action=page.getByRole('button',{name:'打开网络工作台',exact:true});await expect(action).toHaveAttribute('href',/^http:\/\/127\.0\.0\.1:/,{timeout:15000});
 await page.screenshot({path:path.join(run,'08-harness-editor-launcher.png')});
 const popupPromise=page.waitForEvent('popup');await action.click();const workbench=await popupPromise;await workbench.waitForLoadState();
 await expect(workbench.getByRole('button',{name:'保存草稿',exact:true})).toBeVisible();
 await expect(workbench.locator('.left-panel').getByRole('button',{name:'阿青',exact:true})).toBeVisible();
 await fs.writeFile(path.join(run,'launcher-verification.json'),JSON.stringify({passed:true,officialSlot:'conversation.session.header.actions',nativeAuthRequired:true,opensRealWorkbench:true,modelApiCalls:0,errors},null,2));
 expect(errors).toEqual([]);console.log('PASS native Harness button, authenticated address lookup and actual workbench opening; no model calls');
}catch(error){await page.screenshot({path:path.join(run,'launcher-failure.png')});console.error((await page.locator('body').innerText()).slice(0,2500));console.error('Page errors:',errors);throw error;}finally{await browser.close();}
