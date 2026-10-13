import { ToolPermissions } from "./tool-permissions.js";
import { InstructionHistory } from "./instructions.js";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { existsSync } from "node:fs";
import { createUserMessage } from "@deepseek-ai/dsh-llm";
import { Bridge } from "./bridge.js";
import { loadToolboxes } from "./toolbox-catalog.js";
import { here, object, checked } from "./primitives.js";
export function define(r) {
  r.managesAgent = (actor, target, scope = 'self') => {
    if (actor === target) return true;
    const direct = r.recoveryAgents[target]?.manager_id;
    if (scope === 'self') return false;
    if (scope === 'children') return direct === actor;
    const seen = new Set();
    let current = direct;
    while (current && !seen.has(current)) {
      if (current === actor) return true;
      seen.add(current);
      current = r.recoveryAgents[current]?.manager_id;
    }
    return false;
  };
  r.openAgent = async function (binding, options) {
    if (!binding) return r.ctx.agents.create(options);
    try {
      return await r.ctx.agents.resume({
        resumeSessionId: binding.session_id,
        parentAgent: options.parentAgent,
        agentOptions: options.agentOptions,
        setup: options.setup
      });
    } catch (error) {
      if (binding.status === 'prepared' && /not found|does not exist|ENOENT/i.test(String(error))) {
        return r.ctx.agents.create(options);
      }
      throw error;
    }
  };
  r.remember = async function (target, value) {
    const result = await r.bridge.call('bind_agent', {
      target,
      ...value
    });
    r.recoveryAgents[target] = {
      ...r.recoveryAgents[target],
      target,
      ...value,
      manager_id: value.manager_id ?? r.recoveryAgents[target]?.manager_id ?? value.creator_node_id ?? null
    };
    if (result.agents) Object.assign(r.recoveryAgents, result.agents);
  };
  r.prepareAgent = async (ac, actor, role, refs = []) => {
    r.permissions.state(ac);
    const detail={ac,actor,role,refs};
    await r.ctx.serial('datanet/agent-capabilities',detail);
    r.agentDetails.set(ac,detail);
    r.ctx.emit('datanet/agent-tools', {
      ac,
      agentCtx: ac,
      actor,
      role,
      refs,
      ...detail,
      parent: r.scopes.get(ac)?.parent,
      access: async (target, direction, strength = r.scopes.get(ac).maxStrength) => {
        if (!(await r.bridge.call('check_access', {
          actor,
          target,
          direction,
          strength
        })).allowed) throw new Error('Target is outside permitted network path');
      }
    });
  };
  r.bindAgentContext = (ac, agent, actor, role) => {
    r.instructionHistory.bind(ac, agent);
    r.ctx.emit('datanet/agent-bound', {
      ac,
      agent,
      actor,
      role
    });
  };
  r.attachAgentTools = (agentCtx, actor, parent) => {
    const access = async (target, direction = 'read', strength = r.scopes.get(agentCtx).maxStrength) => {
      if (strength > (r.config.maxSignalStrength ?? 4)) throw new Error('Signal strength exceeds root capability');
      if (!(await r.bridge.call('check_access', {
        actor,
        target,
        direction,
        strength
      })).allowed) throw new Error('Target is outside permitted network path');
    };
    r.ctx.emit('datanet/agent-tools', {
      ac: agentCtx,
      agentCtx,
      actor,
      parent,
      access,
      ...r.agentDetails.get(agentCtx)
    });
  };
}
export const steps = [{
  order: 0,
  async run(r) {
    r.permissions = new ToolPermissions(createUserMessage);
    r.agentDetails=new WeakMap();
  }
}, {
  order: 1,
  async run(r) {
    r.register = (ac, name, description, parameters, execute) => {
      if (!r.components.allows(name)) return () => {};
      const owner = r.components.owner(name);
      return r.components.track(owner, r.permissions.register(ac, {
        name,
        description,
        parameters,
        output: {
          schema: {},
          render: (_args, value) => [{
            type: 'text',
            text: JSON.stringify(value)
          }]
        },
        execute: async (...args) => {
          if (!r.components.allows(name)) throw new Error('Tool component is disabled');
          return execute(...args);
        }
      }));
    };
  }
}, {
  order: 2,
  async run(r) {
    r.fields = new Set(['workspace', 'storage', 'rootNetwork', 'rootEntryPoint', 'backend', 'backendArgs', 'maxSignalStrength', 'turnTimeoutMs', 'provider', 'model', 'agentMaxTokens', 'rootToolboxes', 'defaultAgentToolboxes', 'allowedAgentToolboxes', 'toolboxes', 'components',...[...r.components.catalog.values()].flatMap(m=>m.configurationFields??[])]);
  }
}, {
  order: 3,
  async run(r) {
    for (const key of Object.keys(r.config)) if (!r.fields.has(key)) throw new Error(`Unknown config field ${key}; use toolbox configuration`);
  }
}, {
  order: 8,
  async run(r) {
    r.rootPrompt = null;
  }
}, {
  order: 9,
  async run(r) {
    r.workspace = path.resolve(r.config.workspace || path.join(here, 'workspace'));
  }
}, {
  order: 10,
  async run(r) {
    r.directory = path.resolve(r.config.storage || path.join(r.workspace, '.datanet'));
  }
}, {
  order: 11,
  async run(r) {
    await mkdir(r.workspace, {
      recursive: true
    });
  }
}, {
  order: 12,
  async run(r) {
    await mkdir(r.directory, {
      recursive: true
    });
  }
}, {
  order: 24,
  async run(r) {
    r.channelDefinitions = new WeakMap();
    r.openChannels = new WeakMap();
    r.channelEntrances = new WeakMap();
  }
}, {
  order: 25,
  async run(r) {
    r.instructionHistory = new InstructionHistory(createUserMessage);
  }
}, {
  order: 27,
  async run(r) {
    r.loadInstructions = (ac, id, text) => r.instructionHistory.load(ac, id, text);
  }
}, {
  order: 38,
  async run(r) {
    r.privateDisposers = new WeakMap();
  }
}, {
  order: 39,
  async run(r) {
    r.sourcePython = path.join(here, '.venv', 'Scripts', 'python.exe');
    r.sourceServer = path.join(here, 'adapters/harness/backend/server.py');
  }
}, {
  order: 40,
  async run(r) {
    r.useSource = !r.config.backend && existsSync(r.sourcePython) && existsSync(r.sourceServer);
  }
}, {
  order: 41,
  async run(r) {
    r.bridge = new Bridge(r.config.backend || (r.useSource ? r.sourcePython : path.join(here, 'adapters/harness/runtime/backend/datanet-backend.exe')), r.directory, r.config.backendArgs ?? (r.useSource ? [r.sourceServer] : []), {DATANET_PRODUCT_ROOT:here,DATANET_COMPONENT_ROOT:path.join(here,'components'),DATANET_COMPONENT_PROFILE:JSON.stringify(Object.fromEntries([...r.components.catalog.keys()].map(id=>[id,r.components.active(id)])))});
  }
}, {
  order: 42,
  async run(r) {
    await r.bridge.call('ping');
  }
}, {
  order: 43,
  async run(r) {
    try {
      const rootComponent = 'network_presets/' + r.config.rootNetwork;
      if (r.config.rootNetwork && (!r.components.catalog.has(rootComponent) || r.components.active(rootComponent))) checked(await r.bridge.call('load_root_network', {
        package: r.config.rootNetwork,
        entry_point: r.config.rootEntryPoint ?? 'root'
      }));
      const rootInfo = await r.bridge.call('root_network_info');
      if (rootInfo.agent_config) r.rootPrompt = await readFile(rootInfo.agent_config.prompt_path, 'utf8');
    } catch (error) {
      await r.bridge.close();
      throw error;
    }
  }
}, {
  order: 44,
  async run(r) {
    r.registry = r.ctx.get('workspaceRegistry');
  }
}, {
  order: 45,
  async run(r) {
    if (r.registry && !r.registry.list().some(w => path.resolve(w.path) === r.workspace)) await r.registry.create(r.workspace, 'DataNet 插件独立验证');
  }
}, {
  order: 46,
  async run(r) {
    r.sessions = new Map();
  }
}, {
  order: 47,
  async run(r) {
    r.saved = await r.bridge.call('recovery_info');
  }
}, {
  order: 48,
  async run(r) {
    r.recoveryAgents = r.saved.agents;
  }
}, {
  order: 49,
  async run(r) {
    r.restored = false;
  }
}, {
  order: 50,
  async run(r) {
    r.recoveryErrors = [];
  }
}, {
  order: 51,
  async run(r) {
    r.ctx.effect(() => async () => {
      try {
        await Promise.allSettled([...r.sessions.values()].map(({
          handle
        }) => handle.dispose()));
      } finally {
        await r.bridge.close();
      }
    }, 'datanet.runtime');
  }
}, {
  order: 52,
  async run(r) {
    r.toolboxRegistry = await loadToolboxes(path.join(here, 'components', 'toolboxes'), r.config.toolboxes ?? {}, r.components);
  }
}, {
  order: 65,
  async run(r) {
    r.registeredTools = new WeakMap();
  }
}, {
  order: 67,
  async run(r) {
    r.scopes = new WeakMap();
    r.managementLocks = new Set();
  }
}, {
  order: 68,
  async run(r) {
    r.rootAgent = null;
  }
}, {
  order: 75,
  async run(r) {
    r.registerPrivate = (ac, name, description, parameters, execute) => {
      const entry = r.scopes.get(ac);
      if (!entry?.grant.framework.has(name) || !r.components.allows(name)) return;
      if (r.isTemporaryTool?.(name) && !r.temporaryToolsAllowed?.(ac)) return;
      if (r.channelSpecs?.has(name)) {
        let definitions = r.channelDefinitions.get(ac);
        if (!definitions) {
          definitions = new Map();
          r.channelDefinitions.set(ac, definitions);
        }
        definitions.set(name, [name, description, parameters, execute]);
        const spec = r.channelSpecs.get(name);
        if (spec.allowed && !spec.allowed(ac)) return;
        let entrances = r.channelEntrances.get(ac);
        if (!entrances) {
          entrances = new Set();
          r.channelEntrances.set(ac, entrances);
        }
        if (!entrances.has(name)) {
          entrances.add(name);
          r.register(ac, name + '_channel', description, spec.parameters ?? object(), p => r.enterToolChannel(ac, name, p.preset));
        }
        if (!r.openChannels.get(ac)?.has(name)) return;
      }
      let installed = r.registeredTools.get(ac);
      if (!installed) {
        installed = new Set();
        r.registeredTools.set(ac, installed);
      }
      if (installed.has(name)) return;
      installed.add(name);
      const dispose = r.register(ac, name, description, parameters, async (p, exec) => {
        if (!r.components.allows(name)) throw new Error('Tool component is disabled');
        const options = entry.grant.framework.get(name);
        if (!options) throw new Error('Tool is no longer granted');
        if (r.channelSpecs?.has(name) && !r.openChannels.get(ac)?.has(name)) throw new Error('Enter the tool channel first');
        if (parameters.properties?.strength) p = {
          ...p,
          strength: p.strength ?? entry.maxStrength
        };
        if ((p.strength ?? p.arguments?.strength ?? entry.maxStrength) > entry.maxStrength) throw new Error('Signal strength exceeds Agent grant');
        if (options.actions && p.action && !options.actions.includes(p.action)) throw new Error('Action is outside toolbox grant');
        if (options.allow_custom === false && p.prompt) throw new Error('Custom prompts are outside toolbox grant');
        const payload = {
          ac,
          name,
          arguments: p,
          exec,
          entry,
          options,
          parameters
        };
        try {
          await r.ctx.serial('datanet/tool-before', payload);
          const value = await r.ctx.waterfall('datanet/tool-execute', payload, () => execute(payload.arguments, exec));
          await r.ctx.serial('datanet/tool-after', {
            ...payload,
            value
          });
          return value;
        } catch (error) {
          await r.ctx.serial('datanet/tool-error', {
            ...payload,
            error
          });
          throw error;
        }
      });
      let disposers = r.privateDisposers.get(ac);
      if (!disposers) {
        disposers = new Map();
        r.privateDisposers.set(ac, disposers);
      }
      disposers.set(name, dispose);
    };
  }
}, {
  order: 84,
  async run(r) {
    r.optionsFor = (ac, name) => r.scopes.get(ac).grant.framework.get(name) ?? {};
  }
}, {
  order: 86,
  async run(r) {
    r.scoped = agent => {
      const cwd = agent.session.header.cwd;
      return cwd && path.resolve(cwd) === r.workspace;
    };
  }
}, {
  order: 87,
  async run(r) {
    r.trace = async value => writeFile(path.join(r.directory, 'events.jsonl'), JSON.stringify({
      ...value,
      time: new Date().toISOString()
    }) + '\n', {
      flag: 'a'
    });
  }
}, {
  order: 93,
  async run(r) {
    r.route = options => Object.fromEntries(['provider', 'model', 'maxTokens'].filter(k => options[k] !== undefined).map(k => [k, options[k]]));
  }
}];
