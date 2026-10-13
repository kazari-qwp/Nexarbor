import { assertCompleteOutput } from "../../../adapters/harness/framework/response-status.js";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { updateCapabilityTools } from "../../../adapters/harness/framework/capabilities.js";
import { here, compactFeedback, object, str, number, user, checked } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.enterToolChannel = async function (ac, name, preset) {
    const definition = r.channelDefinitions.get(ac)?.get(name),
      spec = r.channelSpecs.get(name);
    if (!definition || !spec || !r.scopes.get(ac)?.grant.framework.has(name) || !r.components.allows(name)) throw new Error('Tool is not granted');
    const payload = {
      ac,
      name,
      preset,
      added: false
    };
    await r.ctx.serial('datanet/channel-enter', payload);
    let opened = r.openChannels.get(ac);
    if (!opened) {
      opened = new Set();
      r.openChannels.set(ac, opened);
    }
    opened.add(name);
    r.registerPrivate(ac, ...definition);
    return {
      tool: name,
      available: true,
      instructions_added: payload.added
    };
  };
}
export const steps = [{
  order: 85,
  async run(r) {
    r.enforceStrength = p => {
      if ((p.strength ?? 0) > (r.config.maxSignalStrength ?? 4)) throw new Error('Signal strength exceeds root capability');
      return p;
    };
  }
}, {
  order: 18,
  async run(r) {
    r.presetGuides = new Map();
    for (const m of r.components.catalog.values()) if (m.preset && m.guide && r.components.active(m.id)) r.presetGuides.set(m.preset, await readFile(path.join(m.directory, m.guide), 'utf8'));
    r.toolGuides = new Map();
    for (const name of ['datanet_create_node', 'datanet_create_agent', 'datanet_manage_agent', 'datanet_interfaces']) {
      const guide = await readFile(path.join(here, 'components/tools/network_management/guides', name, 'AGENTS.md'), 'utf8');
      r.toolGuides.set(name, guide);
      r.channelSpecs.set(name, {
        guide
      });
    }
    r.channelSpecs.set('datanet_create_network', {
      presets: true,
      parameters: object({
        preset: {
          type: 'string',
          enum: [...r.presetGuides.keys()]
        }
      }, ['preset'])
    });
  }
}];
export function install(r) {
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_create_agent', '在获准节点挂载 Agent，选择职责预设与私有工具箱。', object({
      target: str,
      preset: {
        type: 'string',
        enum: Object.keys(r.agentPresets)
      },
      prompt: str,
      toolboxes: {
        type: 'array',
        items: {
          type: 'string',
          enum: r.allowedToolboxes
        },
        uniqueItems: true
      },
      max_signal_strength: number
    }, ['target']), async (p, exec) => {
      if (p.target === 'root' && r.rootAgent) throw new Error('Root already has a native Agent; create a child node and mount there');
      const preset = r.agentPresets[p.preset ?? 'worker'];
      if (!preset) throw new Error('Unknown Agent preset');
      const toolboxNames = p.toolboxes ?? preset.toolboxes ?? r.defaultAgentToolboxes;
      r.resolveAgentToolboxes(toolboxNames, r.allowedToolboxes);
      if (r.sessions.has(p.target)) throw new Error('Node already has an Agent');
      if (p.prompt && r.optionsFor(agentCtx, 'datanet_create_agent').allow_custom === false) throw new Error('Custom Agent creation is disabled');
      const prompt = p.prompt || (await readFile(preset.promptPath, 'utf8'));
      const strength = p.max_signal_strength ?? preset.max_signal_strength ?? 2;
      if (strength > r.scopes.get(agentCtx).maxStrength) throw new Error('Child signal limit exceeds creator grant');
      return r.createNodeAgent(p.target, prompt, exec.agent, strength, toolboxNames, null, undefined, preset.experience_role ?? preset.id, preset.experience_refs ?? []);
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_call_agent', '向已有下属 Agent 委托任务；没有子 Agent 时不要使用本工具，也不要用它代替自己的工作。目标须读可达且符合管理范围；会话上下文保留。讨论成员自身由黑板调度。', object({
      target: str,
      task: str,
      strength: number
    }, ['target', 'task']), async (p, exec) => {
      await access(p.target, 'read', p.strength);
      const member = r.sessions.get(p.target);
      if (!member?.generic) throw new Error('Use discussion scheduling for discussion members');
      if (member.handle.agent.status !== 'idle') throw new Error('Agent is already busy');
      await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, 'execute');
      await r.delegateReport(agentCtx, p.target, p.task, member.handle.agent.ctx);
      await r.diagnostics.start(member.handle.agent.ctx);
      let timedOut = false;
      const cancel = () => member.handle.agent.cancel('user');
      exec.signal?.throwIfAborted();
      exec.signal?.addEventListener('abort', cancel, {
        once: true
      });
      const timer = setTimeout(() => {
        timedOut = true;
        cancel();
      }, r.config.turnTimeoutMs ?? 180000);
      const feedbackBefore = r.feedbackByAgent.get(p.target)?.id;
      const messageStart = member.handle.agent.session.deriveMessages().length;
      try {
        member.handle.agent.followup(user(p.task));
        await member.handle.agent.whenIdle();
        exec.signal?.throwIfAborted();
        if (timedOut) throw new Error('Agent execution timeout');
        const messages = member.handle.agent.session.deriveMessages();
        assertCompleteOutput(messages.slice(messageStart));
        const feedback = r.feedbackByAgent.get(p.target);
        const blocked = feedback && feedback.id !== feedbackBefore;
        if (!blocked && r.diagnostics.states.get(member.handle.agent.ctx)?.failed) throw new Error('Agent execution failed');
        if (!blocked) {
          r.assertProblemClosed(member.handle.agent.ctx);
          await r.diagnostics.completed(member.handle.agent.ctx, JSON.stringify(messages.filter(m => m.role === 'assistant').at(-1)?.content ?? []));
        }
        return {
          report_reference: r.reports.reference(r.reports.context(member.handle.agent.ctx)),
          ...(!blocked ? {
            retry_run_id: r.diagnostics.lastCompleted(member.handle.agent.ctx)
          } : {}),
          status: feedback && feedback.id !== feedbackBefore ? 'blocked' : 'ok',
          ...(feedback && feedback.id !== feedbackBefore ? {
            feedback: compactFeedback(feedback)
          } : {}),
          session_id: member.handle.agent.id,
          message: messages.filter(m => m.role === 'assistant').at(-1) ?? null
        };
      } catch (error) {
        await r.diagnostics.exception(member.handle.agent.ctx, error);
        await r.interruptProblem(member.handle.agent.ctx, error);
        throw error;
      } finally {
        clearTimeout(timer);
        exec.signal?.removeEventListener('abort', cancel);
        await r.ctx.sessions.flush(member.handle.agent.session);
        await r.bridge.call('agent_progress', {
          target: p.target,
          activity: r.feedbackByAgent.get(p.target)?.id !== feedbackBefore ? 'blocked' : 'idle'
        });
      }
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_manage_agent', '查看或调整获准 Agent 的提示词与会话。', object({
      target: str,
      action: {
        type: 'string',
        enum: ['inspect', 'update_prompt', 'restart', 'clear_context']
      },
      prompt: str
    }, ['target', 'action']), async (p, exec) => {
      const member = r.sessions.get(p.target);
      if (!member) throw new Error('Node has no mounted Agent');
      if (p.action === 'inspect') return {
        node_id: p.target,
        session_id: member.handle.agent.id,
        manager_id: r.recoveryAgents[p.target]?.manager_id ?? null,
        managed_ids: r.recoveryAgents[p.target]?.managed_ids ?? [],
        status: member.handle.agent.status,
        toolboxes: member.toolboxes,
        prompt: member.promptState.text,
        prompt_path: member.promptPath,
        creator_node_id: r.recoveryAgents[p.target]?.creator_node_id ?? null
      };
      if (member.handle.agent.status !== 'idle') throw new Error('Agent is busy');
      if (p.action === 'update_prompt') {
        if (typeof p.prompt !== 'string' || !p.prompt.trim()) throw new Error('Prompt required');
        await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, 'update_prompt');
        await writeFile(member.promptPath + '.bak', await readFile(member.promptPath, 'utf8'), 'utf8');
        await writeFile(member.promptPath, p.prompt, 'utf8');
        member.promptState.text = p.prompt;
        await r.remember(p.target, {
          ...r.recoveryAgents[p.target],
          prompt: p.prompt
        });
        return {
          node_id: p.target,
          updated: true,
          context_preserved: true
        };
      }
      if (!member.generic) throw new Error('Discussion members support inspect/update_prompt; restart/reset is scheduler-managed');
      await r.problemChannel.reserveRecovery(agentCtx, p.target, r.feedbackByAgent.get(p.target)?.id, 'restart');
      const prompt = p.prompt ?? (await readFile(member.promptPath, 'utf8'));
      await member.handle.dispose();
      r.sessions.delete(p.target);
      const loaded = [...(r.loadedSkills.get(member.handle.agent.ctx) ?? [])];
      const created = await r.createNodeAgent(p.target, prompt, exec.agent, member.maxStrength, member.baseToolboxes ?? member.toolboxes, null, member.creatorNodeId, r.recoveryAgents[p.target]?.experienceRole, r.recoveryAgents[p.target]?.experienceRefs);
      for (const name of loaded) await r.enableSkill(r.sessions.get(p.target).handle.agent.ctx, name, exec.agent);
      return created;
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_agent_capabilities', '查看宿主允许为子 Agent 装配的工具箱。工具箱私有，不可跨 Agent 调用工具或 Skill。', object(), () => ({
      agent_presets: Object.values(r.agentPresets),
      default: r.defaultAgentToolboxes,
      toolboxes: r.allowedToolboxes.map(id => ({
        id,
        description: r.toolboxRegistry[id]?.description ?? id
      }))
    }));
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_presets', '查看预设预览；指定preset查看网络的详细使用说明。', object({
      preset: {
        type: 'string',
        enum: [...r.presetGuides.keys()]
      }
    }), async p => {
      if (p.preset) {
        const instructions = r.presetGuides.get(p.preset);
        return {
          preset: p.preset,
          instructions_added: r.loadInstructions(agentCtx, 'preset:' + p.preset, instructions)
        };
      }
      return r.bridge.call('agent_capability', {
        actor,
        tool: 'list_node_presets',
        options: r.optionsFor(agentCtx, 'datanet_create_node')
      });
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_interfaces', '查看、新增、修改或删除获准节点的读写接口。', object({
      action: {
        type: 'string',
        enum: r.optionsFor(agentCtx, 'datanet_interfaces').actions ?? ['list', 'add', 'update', 'remove']
      },
      arguments: {
        type: 'object',
        properties: {
          node_id: str,
          direction: {
            type: 'string',
            enum: ['read', 'write']
          },
          target_node_id: {
            type: 'string',
            description: 'add/update/remove必填；即便提供interface_index也须填写，用来核验目标。'
          },
          interface: {
            type: 'object',
            properties: {
              visibility: {
                type: 'string',
                enum: ['private', 'public']
              }
            },
            additionalProperties: false
          },
          changes: {
            type: 'object',
            properties: {
              visibility: {
                type: 'string',
                enum: ['private', 'public']
              }
            },
            additionalProperties: false
          },
          interface_index: {
            type: 'integer',
            minimum: 0
          }
        },
        additionalProperties: false
      }
    }, ['action', 'arguments']), p => r.bridge.call('agent_capability', {
      actor,
      tool: 'manage_interfaces',
      options: r.optionsFor(agentCtx, 'datanet_interfaces'),
      arguments: r.enforceStrength({
        ...p.arguments,
        action: p.action
      })
    }));
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_create_node', '创建数据或组织子节点，可选择预设或自定义受支持类型。', object({
      child_id: str,
      node_spec: {
        type: 'object'
      },
      parent_node_id: str,
      read_interface: {
        type: 'object',
        properties: {
          visibility: {
            type: 'string',
            enum: ['private', 'public']
          }
        },
        additionalProperties: false
      },
      write_interface: {
        type: 'object',
        properties: {
          visibility: {
            type: 'string',
            enum: ['private', 'public']
          }
        },
        additionalProperties: false
      }
    }, ['child_id', 'node_spec']), async p => {
      if (r.optionsFor(agentCtx, 'datanet_create_node').allow_custom === false && !p.node_spec?.preset) throw new Error('Custom node configuration is disabled');
      const result = await r.bridge.call('create_node', {
        ...r.enforceStrength(p),
        actor,
        options: r.optionsFor(agentCtx, 'datanet_create_node')
      });
      await r.ctx.serial('datanet/graph-changed', {
        ac: agentCtx
      });
      return result;
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/agent-tools', ({
    agentCtx,
    actor,
    parent,
    access
  }) => {
    r.registerPrivate(agentCtx, 'datanet_create_network', '选择配置包创建网络；返回structure为新建网络读写连接摘要（实际ID），包括父节点挂载关系。以返回ID操作，不要猜测路径。discussion_group 会挂载五个持久 Harness Agent：project_nodes可引用多个已有查询文本；不提供时必须填写project正文，两者只选一种。number_network 是通用数字网络。', object({
      preset: {
        type: 'string',
        enum: [...r.presetGuides.keys()]
      },
      instance_id: str,
      parent_node_id: str,
      project: str,
      project_nodes: {
        type: 'array',
        items: str,
        minItems: 1,
        uniqueItems: true
      },
      with_agents: {
        type: 'boolean'
      },
      rounds: {
        type: 'integer',
        minimum: 1,
        maximum: 8
      }
    }, ['preset', 'instance_id']), async (p, exec) => {
      if (!r.instructionHistory.has(agentCtx, 'preset:' + p.preset)) throw new Error('Enter the network channel for this preset first');
      if (p.preset === 'discussion_group' && p.with_agents !== false && r.optionsFor(agentCtx, 'datanet_create_agent').scope !== 'descendants') throw new Error('This preset needs Agent creation permission with descendants scope');
      const group = checked(await r.bridge.call('create_network', {
        ...r.enforceStrength(p),
        actor,
        options: r.optionsFor(agentCtx, 'datanet_create_network')
      }));
      if (p.preset === 'discussion_group' && p.with_agents !== false) {
        await r.makeMembers(group, exec.agent);
        r.groups.set(group.group_id, group);
      }
      const structure = group.structure ?? group.items?.[0]?.structure;
      if (structure) for (const node of structure.nodes) {
        const member = r.sessions.get(node.node_id);
        node.agent = member ? {
          mounted: true,
          role: node.node_id === group.leader_id ? 'leader' : node.node_id === group.recorder_id ? 'recorder' : group.members?.includes(node.node_id) ? 'member' : 'agent'
        } : null;
      }
      if (structure) {
        const compact = {
          management: structure.nodes.filter(node => node.management_parent_id).map(node => node.management_parent_id + ' → ' + node.node_id).join('\n')
        };
        for (const direction of ['read', 'write']) {
          const rows = new Map();
          for (const edge of [...structure.attachment_interfaces, ...structure.interfaces]) {
            if (edge.direction !== direction) continue;
            if (!rows.has(edge.source_node_id)) rows.set(edge.source_node_id, new Set());
            rows.get(edge.source_node_id).add(edge.target_node_id);
          }
          compact[direction] = [...rows].map(([source, targets]) => source + ' → ' + [...targets].join(', ')).join('\n');
        }
        if (group.structure) group.structure = compact;else group.items[0].structure = compact;
      }
      await r.ctx.serial('datanet/graph-changed', {
        ac: agentCtx
      });
      await r.bridge.call('save');
      await r.trace({
        type: 'create_network',
        result: group
      });
      return group;
    });
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/channel-enter', async payload => {
    const {
        ac,
        name,
        preset
      } = payload,
      spec = r.channelSpecs.get(name);
    if (spec.allowed && !spec.allowed(ac)) throw new Error('Channel entry is unavailable');
    if (spec.presets && !r.presetGuides.has(preset)) throw new Error('Choose a supported network preset');
    if (r.scopes.get(ac).grant.expanded.includes('network_management')) await r.loadManagementInstructions(ac);
    payload.added = r.loadInstructions(ac, spec.presets ? 'preset:' + preset : 'tool:' + name, spec.presets ? r.presetGuides.get(preset) : spec.guide);
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/tool-before', async payload => {
    let {
      name,
      arguments: p,
      entry,
      options
    } = payload;
    if (['datanet_create_node', 'datanet_create_network'].includes(name)) {
      p = {
        ...p
      };
      for (const direction of ['read', 'write']) {
        const key = direction + '_interface';
        if (p[key]) p[key] = {
          threshold: 0,
          multiplier: 1,
          ...p[key]
        };
      }
      if (name === 'datanet_create_node' && p.node_spec && !p.node_spec.preset) p.node_spec = {
        parameters: {},
        ...p.node_spec
      };
    }
    if (name === 'datanet_interfaces') {
      if (p.action !== 'list' && !p.arguments?.target_node_id) throw new Error('target_node_id is required for add/update/remove');
      p = {
        ...p,
        arguments: {
          ...p.arguments
        }
      };
      if (p.arguments.interface) p.arguments.interface = {
        threshold: 0,
        multiplier: 1,
        ...p.arguments.interface
      };
    }
    payload.arguments = p;
    if (['datanet_create_agent', 'datanet_call_agent', 'datanet_manage_agent'].includes(name)) {
      const direction = name === 'datanet_call_agent' || p.action === 'inspect' ? 'read' : 'write';
      const result = name === 'datanet_manage_agent' && r.recoveryAgents[p.target] ? {
        allowed: r.managesAgent(entry.actor, p.target, options.scope ?? 'self')
      } : await r.bridge.call(name === 'datanet_call_agent' ? 'check_delegation' : 'check_management', {
        actor: entry.actor,
        target: p.target,
        direction,
        scope: options.scope ?? 'self',
        strength: p.strength ?? entry.maxStrength
      });
      if (!result.allowed) throw new Error('Target is outside management grant');
    }
  });
  r.components.on("tools/network_management", r.ctx, 'datanet/tool-execute', async ({
    name,
    arguments: p
  }, next) => {
    if (!['datanet_create_agent', 'datanet_call_agent', 'datanet_manage_agent'].includes(name)) return next();
    if (r.managementLocks.has(p.target)) throw new Error('Target Agent is busy');
    r.managementLocks.add(p.target);
    try {
      return await next();
    } finally {
      r.managementLocks.delete(p.target);
    }
  });
}
export function fallback(r) {
  r.channelSpecs = new Map();
  r.presetGuides = new Map();
  r.toolGuides = new Map();
  r.enterToolChannel = async () => {
    throw new Error('Tool channels are disabled');
  };
}
