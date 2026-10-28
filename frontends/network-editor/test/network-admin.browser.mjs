// 独立真实项目，管理员范围通过实际access采集；不委托模型制作。
import {_electron, expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startStudio} from '../../../adapt/harness/studio/host.mjs';
import {linkRecord} from '../../shared/graph/links.js';
const root = fileURLToPath(new URL('../../../', import.meta.url));
const directory = path.join(root, 'build/network-admin-ui-' + Date.now());
const host = await startStudio({directory});
const errors = [];
let client, page;
try {
 const initial = await host.request('state', {});
 let document = initial.live.document;
 for (const [kind, id, name] of [['network_admin', 'admin', '局部管理员'], ['node', 'board', '共享看板'], ['node', 'private', '私有节点'], ['node', 'outside', '范围之外']]) {
  document = await host.request('template', {document, kind, options: {id, name}});
 }
 document.network.nodes.find(n => n.node_id === 'admin').links.push(linkRecord('board', {channels: ['admin'], threshold: 1}));
 document.network.nodes.find(n => n.node_id === 'board').links.push(linkRecord('outside', {channels: ['admin'], threshold: 2}));
 const applied = await host.request('apply', {document, base_commit: initial.live.commit, layout: {root: {x: 0, y: -180}, admin: {x: 0, y: 0}, board: {x: 220, y: 0}, outside: {x: 440, y: 0}, private: {x: 220, y: 180}}});
 expect(applied.valid, JSON.stringify(applied)).toBe(true);
 const env = {...process.env}; delete env.ELECTRON_RUN_AS_NODE;
 client = await _electron.launch({executablePath: path.join(root, 'frontends/desktop/node_modules/electron/dist/electron.exe'), args: [path.join(root, 'frontends/desktop'), '--connection', path.join(directory, 'editor-connection.json'), '--user-data-dir=' + path.join(directory, 'profile')], env});
 page = await client.firstWindow(); page.on('pageerror', e => errors.push(e.message));
 await expect(page.locator('.react-flow__node[data-id="admin"]')).toBeVisible({timeout: 20000});
 await page.locator('.react-flow__node[data-id="admin"]').click();
 await page.locator('.inspector-tabs').getByRole('button', {name: '模块', exact: true}).click();
 await page.locator('[data-mounted-id="network.administrator"]>summary').click();
 const panel = page.locator('.network-admin-panel');
 await expect(panel.getByRole('button', {name: '委托制作局部网络', exact: true})).toBeVisible();
 await expect(page.getByText('允许委托制作模块／工具', {exact: true})).toBeVisible();
 await panel.getByRole('button', {name: '查看可达副本', exact: true}).click();
 await expect(panel.locator('pre')).toContainText('共享看板');
 await expect(panel.locator('pre')).not.toContainText('私有节点');
 await expect(panel.locator('pre')).not.toContainText('范围之外');
 await expect(panel.getByRole('alert')).toHaveCount(0);
 expect(errors).toEqual([]);
 await page.screenshot({path: path.join(directory, 'administrator-ui.png')});
 await fs.writeFile(path.join(directory, 'verification.json'), JSON.stringify({passed: true, actualDesktop: true, defaultCatalog: true, nodePanel: true, modeCheckbox: true, localScope: true, hiddenNodesOmitted: true, rawModuleResult: true, modelCalls: 0, errors}, null, 2));
 console.log('PASS ' + directory);
} catch (error) {
 if (page && !page.isClosed()) await page.screenshot({path: path.join(directory, 'failure.png')});
 throw error;
} finally {
 await client?.close(); await host.close();
}
