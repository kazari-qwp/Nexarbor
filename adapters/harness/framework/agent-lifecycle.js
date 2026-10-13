import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import path from "node:path";
import { existsSync } from "node:fs";
import { applyCapabilities } from "./capabilities.js";
import { resolveToolboxes } from "../../../adapters/harness/framework/toolbox-catalog.js";
import { here } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.createNodeAgent = async function (target, prompt, parent, maxStrength = 2, toolboxNames = r.defaultAgentToolboxes, binding = null, creatorOverride = undefined, role = null, refs = []) {
    const extension={actor:target,binding,role,refs,componentData:binding?.componentData??{}};
    await r.ctx.serial('datanet/agent-configure',extension);
    role=extension.role;refs=extension.refs;
    const creatorNodeId = creatorOverride !== undefined ? creatorOverride : binding ? binding.creator_node_id ?? null : r.scopes.get(parent.ctx)?.actor ?? null;
    const promptPath = path.join(r.directory, 'agents', Buffer.from(target).toString('hex') + '.md');
    await mkdir(path.dirname(promptPath), {
      recursive: true
    });
    await writeFile(promptPath, prompt, 'utf8');
    const sessionId = binding?.session_id ?? 'datanet-' + randomUUID();
    const agentOptions = binding?.agentOptions ?? {
      ...r.route(parent.options),
      maxTokens: r.config.agentMaxTokens ?? 4096
    };
    const grant = r.resolveAgentToolboxes(toolboxNames, r.allowedToolboxes);
    const promptState = {
      text: prompt
    };
    if (!binding) await r.remember(target, {
      session_id: sessionId,
      kind: 'generic',
      componentData:extension.componentData,
      creator_node_id: creatorNodeId,
      prompt,
      promptPath,
      maxStrength,
      toolboxes: grant.names,
      agentOptions,
      status: 'prepared'
    });
    const handle = await r.openAgent(binding, {
      sessionId,
      parentAgent: parent,
      meta: {
        cwd: r.workspace,
        agentPreset: binding?.officialPreset ?? 'standard'
      },
      agentOptions,
      async setup(ac, agent) {
        r.scopes.set(ac, {
          grant,
          actor: target,
          maxStrength
        });
        await r.prepareAgent(ac, target, role, refs);
        r.bindAgentContext(ac, agent, target, role);
        const official = await applyCapabilities(ac, agent, grant.official, r.ctx, binding?.officialPreset, r.permissions);
        await r.remember(target, {
          ...r.recoveryAgents[target],
          officialPreset: official.officialPreset
        });
        await r.trace({
          type: 'capabilities',
          actor: target,
          session: agent.id,
          toolboxes: grant.names,
          ...official
        });
        await r.ctx.serial('datanet/graph-changed', {
          ac: ac
        });
        r.attachAgentTools(ac, target, agent);
        await r.ctx.serial('datanet/agent-tools-ready',{ac,agent,actor:target});
        r.components.on("foundation", ac, 'agent/request', async (_payload, next) => {
          await r.ctx.sessions.flush(agent.session);
          await r.bridge.call('agent_progress', {
            target,
            activity: 'running'
          });
          return next();
        });
        r.components.section("foundation", ac, {
          name: 'datanet:node-role',
          order: 90,
          interpolate: false,
          text: () => promptState.text + `\n所属节点：${target}。访问必须从该节点出发。`
        });
      }
    });
    r.ctx.sessionTitle.rename(handle.agent.session, 'DataNet · ' + target);
    await r.ctx.sessions.flush(handle.agent.session);
    await r.remember(target, {
      ...r.recoveryAgents[target],
      status: 'ready',
      activity: binding?.activity === 'running' ? 'interrupted' : 'idle'
    });
    r.sessions.set(target, {
      handle,
      generic: true,
      promptPath,
      maxStrength,
      parent,
      toolboxes: r.scopes.get(handle.agent.ctx).grant.names,
      baseToolboxes: toolboxNames,
      promptState,
      creatorNodeId
    });
    await writeFile(path.join(r.directory, 'agents', Buffer.from(target).toString('hex') + '.json'), JSON.stringify({
      target,
      promptPath,
      maxStrength,
      toolboxes: grant.names,
      session: handle.agent.id
    }, null, 2));
    await r.ctx.serial('datanet/agent-ready',{actor:target,agent:handle.agent,ac:handle.agent.ctx});
    return {
      node_id: target,
      manager_id: r.recoveryAgents[target].manager_id,
      creator_node_id: creatorNodeId,
      session_id: handle.agent.id,
      prompt_path: promptPath,
      toolboxes: grant.names
    };
  };
}
export const steps = [{
  order: 53,
  async run(r) {
    r.agentDefaults=Object.assign({},...[...r.components.catalog.values()].filter(m=>r.components.active(m.id)&&m.agentDefaults).map(m=>m.agentDefaults));
    r.allowedToolboxes=r.config.allowedAgentToolboxes??r.agentDefaults.allowedToolboxes??[];
  }
}, {
  order: 54,
  async run(r) {
    r.defaultAgentToolboxes = r.config.defaultAgentToolboxes ?? r.agentDefaults.toolboxes ?? [];
  }
}, {
  order: 56,
  async run(r) {
    for (const id of r.allowedToolboxes) resolveToolboxes(r.toolboxRegistry, [id], r.allowedToolboxes);
  }
}, {
  order: 57,
  async run(r) {
    r.resolveAgentToolboxes = (names, allowed, {
      role = null
    } = {}) => {
      const policies=[...r.components.catalog.values()].filter(m=>m.agentPolicy&&r.components.active(m.id));
      const selected=names.filter(id=>!policies.some(m=>m.id==='toolboxes/'+id&&m.agentPolicy.baseline));
      const grant = resolveToolboxes(r.toolboxRegistry, selected, allowed);
      const defaults=policies.filter(m=>m.agentPolicy.baseline&&!(m.agentPolicy.exceptRoles??[]).includes(role)).map(m=>m.id.split('/')[1]);
      const baseline = resolveToolboxes(r.toolboxRegistry, defaults);
      for (const [name, options] of baseline.framework) if (!grant.framework.has(name)) grant.framework.set(name, options);
      for (const name of [...grant.framework.keys()]) if (!r.components.allows(name)) grant.framework.delete(name);
      grant.names = [...new Set([...grant.names, ...defaults])];
      grant.expanded = [...new Set([...grant.expanded, ...baseline.expanded])];
      return grant;
    };
  }
}, {
  order: 58,
  async run(r) {
    r.rootGrant = r.resolveAgentToolboxes(r.config.rootToolboxes ?? r.agentDefaults.rootToolboxes ?? []);
  }
}, {
  order: 59,
  async run(r) {
    resolveToolboxes(r.toolboxRegistry, r.defaultAgentToolboxes, r.allowedToolboxes);
  }
}, {
  order: 61,
  async run(r) {
    r.agentPresets = {};
  }
}, {
  order: 62,
  async run(r) {
    for (const m of r.components.catalog.values()) if (m.agentPreset && r.components.active(m.id)) {
      const preset = m.agentPreset;
      r.agentPresets[preset.id] = {
        ...preset,
        promptPath: path.join(m.directory, preset.prompt),
        description: preset.description ?? preset.id
      };
    }
  }
}, {
  order: 98,
  async run(r) {
    r.components.on("foundation", r.ctx, 'agent/created', async ({
      agent
    }) => {
      if (!r.scoped(agent) || r.scopes.has(agent.ctx) || agent.session.header.origin === 'subagent') return;
      r.rootAgent = agent;
      const extension={actor:'root',binding:r.recoveryAgents.root,role:null,refs:[],componentData:r.recoveryAgents.root?.componentData??{}};
      await r.ctx.serial('datanet/agent-configure',extension);
      await r.remember('root', {
        ...(r.recoveryAgents.root ?? {}),
        session_id: agent.session.id,
        kind: 'root',componentData:extension.componentData,
        creator_node_id: null,
        activity: 'idle'
      });
      r.scopes.set(agent.ctx, {
        grant: r.rootGrant,
        actor: 'root',
        maxStrength: r.config.maxSignalStrength ?? 4
      });
      await r.prepareAgent(agent.ctx, 'root', extension.role,extension.refs);
      r.bindAgentContext(agent.ctx, agent, 'root', extension.role);
      const official = await applyCapabilities(agent.ctx, agent, r.rootGrant.official, r.ctx, undefined, r.permissions);
      await r.trace({
        type: 'capabilities',
        actor: 'root',
        session: agent.id,
        toolboxes: r.rootGrant.names,
        ...official
      });
      r.ctx.emit("datanet/root-role", {
        agent: agent,
        prompt: r.rootPrompt
      });
      await r.ctx.serial('datanet/graph-changed', {
        ac: agent.ctx
      });
      r.attachAgentTools(agent.ctx, 'root', agent);
      await r.ctx.serial('datanet/agent-tools-ready',{ac:agent.ctx,agent,actor:'root'});
      await r.ctx.serial('datanet/agent-ready',{ac:agent.ctx,agent,actor:'root'});
      if (!r.restored) {
        r.restored = true;
        await r.ctx.serial('datanet/restore-agents', {
          agent
        });
        for (const binding of Object.values(r.recoveryAgents).filter(x => x.kind === 'generic')) {
          try {
            if (!r.scopes.get(agent.ctx).grant.framework.has('datanet_create_agent')) throw new Error('Agent restoration disabled by toolboxes');
            if (binding.maxStrength > (r.config.maxSignalStrength ?? 4)) throw new Error('Saved signal limit exceeds current host grant');
            await r.createNodeAgent(binding.target, binding.prompt, agent, binding.maxStrength, binding.toolboxes ?? r.defaultAgentToolboxes, binding);
          } catch (error) {
            r.recoveryErrors.push({
              target: binding.target,
              error: String(error)
            });
          }
        }
      }
    });
  }
}];
