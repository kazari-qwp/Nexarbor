// 在新项目build目录运行原客户端，原项目只作为只读代码和静态资源来源。
import {_electron, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const original = path.resolve(process.argv[2]);
const directory = path.join(root, 'build/original-client-reference-' + Date.now());
await fs.mkdir(directory, {recursive: true});
const {startStudio} = await import(pathToFileURL(path.join(original, 'adapters/harness/studio/host.mjs')).href);
const host = await startStudio({directory, python: path.join(root, '.venv-runtime/Scripts/python.exe')});
const errors = [], apiErrors = [];
let client, page;
try {
 const env = {...process.env, NEXARBOR_ROOT: original, PYTHONDONTWRITEBYTECODE: '1'};
 delete env.ELECTRON_RUN_AS_NODE;
 client = await _electron.launch({
  executablePath: path.join(root, 'frontends/desktop/node_modules/electron/dist/electron.exe'),
  args: [path.join(original, 'frontends/desktop'), '--connection', path.join(directory, 'editor-connection.json'), '--user-data-dir=' + path.join(directory, 'profile')], env
 });
 page = await client.firstWindow();
 page.on('pageerror', error => errors.push(error.message));
 page.on('response', response => {
  if (response.url().endsWith('/api') && response.status() >= 400) apiErrors.push({operation: response.request().postDataJSON()?.operation, status: response.status()});
 });
 await expect(page.locator('.react-flow__node')).toHaveCount(1, {timeout: 30000});
 await expect(page.getByRole('region', {name: '书签区', exact: true})).toBeVisible();
 await expect(page.getByRole('region', {name: '历史区', exact: true})).toBeVisible();
 await page.locator('.react-flow__node').click();
 await page.locator('.inspector-tabs').getByRole('button', {name: '属性', exact: true}).click();
 await expect(page.getByLabel('节点名称', {exact: true})).toBeVisible();
 await page.screenshot({path: path.join(directory, 'original-overview.png')});
 const menu = await client.evaluate(({Menu}) => Menu.getApplicationMenu().items.map(item => ({label: item.label, entries: item.submenu?.items.map(child => child.label)})));
 await client.evaluate(({Menu}) => Menu.getApplicationMenu().items.find(item => item.label === '设置').submenu.items.find(item => item.label === '外部文本编辑器与快捷键').click());
 await expect(page.getByRole('dialog', {name: '客户端设置', exact: true})).toBeVisible();
 await page.screenshot({path: path.join(directory, 'original-settings.png')});
 const settings = await page.getByRole('dialog', {name: '客户端设置', exact: true}).innerText();
 await page.getByRole('button', {name: '关闭客户端设置', exact: true}).click();
 await client.evaluate(({Menu}) => Menu.getApplicationMenu().items.find(item => item.label === '设置').submenu.items.find(item => item.label === '资源归档').click());
 await expect(page.getByRole('dialog', {name: '资源归档', exact: true})).toBeVisible();
 await page.screenshot({path: path.join(directory, 'original-archive.png')});
 await page.getByRole('button', {name: '关闭资源归档', exact: true}).click();
 const catalog = await host.request('catalog', {});
 expect(errors).toEqual([]);
 await fs.writeFile(path.join(directory, 'verification.json'), JSON.stringify({passed: true, actualOriginalDesktop: true, originalCode: original, isolatedDirectory: directory, menu, moduleIds: Object.keys(catalog.modules), settings, errors, apiErrors, paidCalls: 0, screenshots: ['original-overview.png', 'original-settings.png', 'original-archive.png']}, null, 2));
 console.log('PASS ' + directory);
} catch (error) {
 if (page && !page.isClosed()) await page.screenshot({path: path.join(directory, 'failure.png')});
 throw error;
} finally {
 await client?.close();
 await host.close();
}
