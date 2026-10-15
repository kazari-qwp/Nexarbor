// Owned-workspace Python startup; the official pwsh executor still confines every command.
import path from 'node:path';
import {mkdir, writeFile} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
const exec = promisify(execFile), prepared = new Map();
const quote = value => "'" + value.replaceAll("'", "''") + "'";

export function prepareWindowsPythonTerminal(workspace) {
  const root = path.resolve(workspace);
  if (!prepared.has(root)) {
    const pending = prepare(root).catch(error => { prepared.delete(root); throw error; });
    prepared.set(root, pending);
  }
  return prepared.get(root);
}

async function prepare(root) {
  const base = path.join(root, '.datanet', 'runtime', 'windows-python');
  const temporary = path.join(root, '.datanet', 'tmp');
  await mkdir(temporary, {recursive: true});
  const options = {windowsHide: true, timeout: 60000, maxBuffer: 1024 * 1024, env: {...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8"}};
  // A private environment uses site-package startup, independent of model PYTHONPATH edits.
  try { await exec('python', ['-m', 'venv', '--without-pip', '--system-site-packages', base], options); }
  catch (error) {
    if (error.code === 'ENOENT') return {python: null, scripts: null, temporary};
    throw error;
  }
  const python = path.join(base, 'Scripts', 'python.exe');
  const {stdout} = await exec(python, ['-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'], options);
  const site = stdout.trim();
  if (path.relative(base, site).startsWith('..') || path.isAbsolute(path.relative(base, site))) throw new Error('Python environment site path is outside its workspace runtime');
  const bridge = fileURLToPath(new URL('../compat/windows_python/_datanet_private_dirs.py', import.meta.url));
  await writeFile(path.join(site, 'datanet_sandbox.pth'), 'import runpy; runpy.run_path(' + JSON.stringify(bridge).replace(/[^\x00-\x7f]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")) + ')["install"]()\n');
  return {python, scripts: path.join(base, 'Scripts'), temporary};
}

export function windowsPythonCommand(command, environment) {
  return (environment.scripts ? '$env:PATH=' + quote(environment.scripts + ';') + '+$env:PATH\n' : '') +
    '$env:TEMP=' + quote(environment.temporary) + '\n$env:TMP=' + quote(environment.temporary) + '\n' + command;
}

export function windowsPythonFailureHint(result) {
  if (!result?.isError && result?.value?.exitCode === 0) return;
  const text = (result?.content ?? []).filter(b => b.type === 'text').map(b => b.text).join('\n');
  if (/ModuleNotFoundError|ImportError/.test(text)) return 'Python 导入失败：将 workdir 设为包含目标包的项目根目录；确认依赖文件已同步。';
  if (/PermissionError/.test(text)) return 'Python 写入被拒绝：核对目标是否在工作区或 $env:TEMP；临时文件使用 tempfile 的默认目录。';
}

export function installWindowsTerminal(ctx, agent, workspace) {
  if (process.platform !== 'win32') return;
  const own = exec => !exec.agent || exec.agent === agent;
  ctx.on('tools/execute', async (exec, next) => {
    if (!own(exec) || exec.name !== 'pwsh' || typeof exec.arguments?.command !== 'string') return next();
    const original = exec.arguments;
    const environment = await prepareWindowsPythonTerminal(workspace);
    exec.arguments = {...original, command: windowsPythonCommand(original.command, environment)};
    try { return await next(); }
    finally { exec.arguments = original; }
  });
  ctx.on('tools/post-execute', async (exec, result, next) => {
    const decision = await next();
    if (!own(exec) || exec.name !== 'pwsh' || decision.kind !== 'accept' || 'value' in decision) return decision;
    const hint = windowsPythonFailureHint(result);
    return hint ? {...decision, content: [...(decision.content ?? result.content), {type:'text', text:hint}]} : decision;
  });
}
