import {_electron, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const directory = path.join(root, 'build/aggregation-e2e-' + Date.now());
let host = await startStudio({directory}), client, page;
const errors = [], apiErrors = [];
const api = async (operation, params = {}) => {
 const response = await fetch('http://' + host.authority + '/api', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-Nexarbor-Token': new URL(host.url).hash.slice(7)},
  body: JSON.stringify({operation, params})
 });
 const result = await response.json();
 if (result.error) throw Error(result.error);
 return result.value;
};
const node = id => page.locator('.react-flow__node[data-id="' + id + '"]');
const current = async () => (await api('state')).live.document.network.nodes.find(n => n.node_id === 'junction');
const launch = async () => {
 const env = {...process.env};
 delete env.ELECTRON_RUN_AS_NODE;
 client = await _electron.launch({
  executablePath: path.join(root, 'frontends/desktop/node_modules/electron/dist/electron.exe'),
  args: [path.join(root, 'frontends/desktop'), '--connection', path.join(directory, 'editor-connection.json'), '--user-data-dir=' + path.join(directory, 'profile')], env
 });
 page = await client.firstWindow();
 page.on('pageerror', e => errors.push(e.message));
 page.on('response', async response => {
  if (response.url().endsWith('/api') && response.status() >= 400) {
   apiErrors.push({operation: response.request().postDataJSON()?.operation, status: response.status()});
  }
 });
 await expect(node('junction')).toBeVisible({timeout: 20000});
 await node('junction').click();
 await expect(page.getByLabel('信号汇总方式', {exact: true})).toBeVisible();
};
try {
 const initial = await api('state');
 const document = await api('template', {document: initial.live.document, kind: 'node', options: {id: 'junction', name: '信号汇合节点'}});
 document.network.nodes.find(n => n.node_id === 'junction').aggregation = 'max';
 const applied = await api('apply', {document, base_commit: initial.live.commit, layout: {root: {x: 0, y: 0}, junction: {x: 220, y: 0}}});
 expect(applied.valid).toBe(true);
 await launch();
 const selector = page.getByLabel('信号汇总方式', {exact: true});
 await expect(selector).toHaveValue('max');
 expect(await selector.locator('option').allTextContents()).toEqual(['求和', '最大值', '最小值', '平均值']);
 for (const value of ['sum', 'min', 'average', 'max']) {
  await selector.selectOption(value);
  await page.getByRole('button', {name: '校验并更新网络', exact: true}).click();
  await expect.poll(async () => (await current()).aggregation).toBe(value);
  await expect(page.getByRole('button', {name: 'Commit', exact: true})).toBeEnabled();
 }
 await page.screenshot({path: path.join(directory, 'aggregation-modes.png')});
 const head = (await api('project.info')).head;
 await page.getByRole('button', {name: 'Commit', exact: true}).click();
 await expect.poll(async () => (await api('project.info')).head).not.toBe(head);
 await client.close(); client = null;
 await host.close(); host = await startStudio({directory});
 await launch();
 await expect(page.getByLabel('信号汇总方式', {exact: true})).toHaveValue('max');
 expect((await current()).aggregation).toBe('max');
 expect(errors).toEqual([]);
 await page.screenshot({path: path.join(directory, 'aggregation-reopened.png')});
 await fs.writeFile(path.join(directory, 'verification.json'), JSON.stringify({passed: true, desktop: true, modes: ['sum', 'max', 'min', 'average'], eachModeApplied: true, commitAndColdReopen: true, modelCalls: 0, errors, apiErrors}, null, 2));
 console.log('PASS ' + directory);
} catch (error) {
 if (page && !page.isClosed()) {
  await page.screenshot({path: path.join(directory, 'failure.png')});
  await fs.writeFile(path.join(directory, 'failed.txt'), await page.locator('body').innerText());
 }
 throw error;
} finally {
 await client?.close();
 await host.close();
}
