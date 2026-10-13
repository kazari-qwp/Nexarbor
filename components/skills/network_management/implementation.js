import { object, str } from "../../../adapters/harness/framework/primitives.js";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { resolveToolboxes } from "../../../adapters/harness/framework/toolbox-catalog.js";
import { here } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.loadManagementInstructions = async function (ac) {
    if (!r.loadInstructions(ac, 'network_management', r.managementGuide)) return;
    const entries = await r.experienceStore.query({
      selectors: [{
        kind: 'toolbox',
        id: 'network_management'
      }],
      status: 'verified',
      core_only: true,
      limit: 10
    });
    const view = r.experienceViews.get(ac);
    for (const e of entries) {
      view?.add(e);
      view?.resident.add(e.id);
    }
  };
  r.enableSkill = async function (ac, name, parent, persist = true) {
    const entry = r.scopes.get(ac),
      pkg = r.skillPackages[name];
    if (!pkg || !(entry.grant.framework.get('datanet_skill')?.skills ?? []).includes(name)) throw new Error('Skill is not granted to this Agent');
    let loaded = r.loadedSkills.get(ac);
    if (!loaded) {
      loaded = new Set();
      r.loadedSkills.set(ac, loaded);
    }
    const loadGuide = () => {
      const added = r.loadInstructions(ac, 'skill:' + name, [pkg.files[pkg.entry], ...pkg.references.filter(reference => !(name === 'network_management' && reference === 'AGENTS.md')).map(reference => '\n## 参考：' + reference + '\n' + pkg.files[reference])].join('\n'));
      return name === 'network_management' ? r.loadManagementInstructions(ac).then(() => added) : Promise.resolve(added);
    };
    if (loaded.has(name)) return {
      name,
      loaded: true,
      already_loaded: true,
      instructions_added: persist ? await loadGuide() : false,
      toolboxes: pkg.toolboxes,
      references: pkg.references
    };
    entry.grant = r.resolveAgentToolboxes([...new Set([...entry.grant.names, ...pkg.toolboxes])], undefined, {
      role: r.recoveryAgents[entry.actor]?.kind
    });
    r.messaging.refresh(entry.actor);
    await r.prepareAgent(ac, entry.actor);
    r.attachData(ac, entry.actor, entry.maxStrength);
    r.attachAgentTools(ac, entry.actor, parent);
    const instructionsAdded = persist ? await loadGuide() : false;
    loaded.add(name);
    if (persist) await r.remember(entry.actor, {
      ...(r.recoveryAgents[entry.actor] ?? {}),
      kind: r.recoveryAgents[entry.actor]?.kind ?? 'root',
      creator_node_id: r.recoveryAgents[entry.actor]?.creator_node_id ?? null,
      loadedSkills: [...loaded]
    });
    const session = r.sessions.get(entry.actor);
    if (session) session.toolboxes = entry.grant.names;
    await r.trace({
      type: 'load_skill',
      actor: entry.actor,
      name,
      toolboxes: pkg.toolboxes
    });
    return {
      name,
      loaded: true,
      instructions_added: instructionsAdded,
      toolboxes: pkg.toolboxes,
      references: pkg.references
    };
  };
  r.restoreSkills = async function (ac, parent) {
    for (const name of r.recoveryAgents[r.scopes.get(ac).actor]?.loadedSkills ?? []) await r.enableSkill(ac, name, parent, false);
  };
}
export const steps = [{
  order: 16,
  async run(r) {
    r.managementGuide = await readFile(path.join(here, 'components/skills/network_management/resources/AGENTS.md'), 'utf8');
  }
}, {
  order: 63,
  async run(r) {
    r.skillPackages = {};
  }
}, {
  order: 64,
  async run(r) {
    for (const folder of ['network_management']) {
      const directory = path.join(here, 'components/skills', folder, 'resources');
      const manifest = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'));
      if (manifest.id !== folder || !Array.isArray(manifest.references) || !manifest.entry) throw new Error('Invalid capability Skill package');
      const grant = resolveToolboxes(r.toolboxRegistry, manifest.toolboxes);
      if (grant.official.tools.length || grant.official.skills === '*' || grant.official.skills.length || grant.official.skillProviders.length) throw new Error('Capability Skills currently support framework toolboxes only');
      const files = {};
      for (const relative of [manifest.entry, ...manifest.references]) {
        const file = path.resolve(directory, relative);
        if (!file.startsWith(directory + path.sep)) throw new Error('Skill resource must stay inside package');
        files[relative] = await readFile(file, 'utf8');
      }
      r.skillPackages[folder] = {
        ...manifest,
        files
      };
    }
  }
}];
export function install(r) {
  r.components.on('skills/network_management',r.ctx,'datanet/agent-tools-ready',async({ac,agent})=>{await r.restoreSkills(ac,agent);});
  r.components.on("skills/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    const skillNames=r.scopes.get(agentCtx).grant.framework.get('datanet_skill')?.skills??[];
    r.registerPrivate(agentCtx, 'datanet_skill', '列出或加载获准能力包。load同时加载Skill文档并授予包声明的工具箱，无逐项二次授权；read按需读取已加载Skill的参考。', object({
      action: {
        type: 'string',
        enum: ['list', 'load', 'read']
      },
      name: {
        type: 'string',
        enum: r.scopes.get(agentCtx).grant.framework.get('datanet_skill')?.skills ?? []
      },
      reference: str
    }, ['action']), async (p, exec) => {
      if (p.action === 'list') return {
        skills: skillNames.map(id => ({
          id,
          description: r.skillPackages[id].description,
          loaded: r.loadedSkills.get(agentCtx)?.has(id) ?? false
        }))
      };
      if (!skillNames.includes(p.name)) throw new Error('Skill is not granted to this Agent');
      if (p.action === 'load') return r.enableSkill(agentCtx, p.name, exec.agent);
      const pkg = r.skillPackages[p.name];
      if (!r.loadedSkills.get(agentCtx)?.has(p.name)) throw new Error('Load this Skill first');
      if (!pkg.references.includes(p.reference)) throw new Error('Unknown Skill reference');
      return {
        name: p.name,
        reference: p.reference,
        instructions_added: r.loadInstructions(agentCtx, p.name === 'network_management' && p.reference === 'AGENTS.md' ? 'network_management' : 'skill:' + p.name + ':' + p.reference, pkg.files[p.reference])
      };
    });
  });
}
export function fallback(r) {
  r.loadedSkills=new WeakMap();
  r.restoreSkills = async () => {};
  r.loadManagementInstructions = async () => {};
  r.skillPackages = {};
}
