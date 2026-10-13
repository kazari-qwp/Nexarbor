import { ExperienceStore, ExperienceView } from "./store.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { here, object, str } from "../../../adapters/harness/framework/primitives.js";
export function define(r) {
  r.loadToolExperience = async function (ac, tool) {
    const view = r.experienceViews.get(ac);
    if (!view || !r.problemChannel.state(ac)) return;
    const contains = id => r.toolboxRegistry[id].tools.some(item => item.name === tool) || (r.toolboxRegistry[id].includes ?? []).some(contains);
    const boxes = r.scopes.get(ac).grant.expanded.filter(contains);
    await view.use(tool, boxes);
    const ids = boxes.flatMap(id => r.toolboxRegistry[id].experience_refs ?? []);
    for (const e of ids.length ? await r.experienceStore.query({
      ids,
      status: 'verified',
      limit: 6
    }) : []) view.add(e);
  };
}
export const steps = [{
  order: 6,
  async run(r) {
    for (const refs of [r.config.rootExperienceRefs ?? []]) if (!Array.isArray(refs) || refs.length > 10 || refs.some(x => typeof x !== 'string' || !x)) throw new Error('Invalid experience references');
  }
}, {
  order: 13,
  async run(r) {
    r.experienceStore = new ExperienceStore(r.config.experienceDirectory ?? path.join(r.directory, 'experiences'));
  }
}, {
  order: 14,
  async run(r) {
    await r.experienceStore.init(JSON.parse(await readFile(path.join(here, 'components/toolboxes/experience/seed.json'), 'utf8')));
  }
}, {
  order: 15,
  async run(r) {
    r.experienceViews = new WeakMap();
  }
}];
export function install(r) {
  r.components.on('toolboxes/experience',r.ctx,'datanet/agent-configure',detail=>{
    const saved=detail.binding?.componentData?.experience;
    detail.role=saved?.role??detail.binding?.experienceRole??detail.role??(detail.actor==='root'?r.config.rootExperienceRole??'project_root':null);
    detail.refs=saved?.refs??detail.binding?.experienceRefs??(detail.actor==='root'?r.config.rootExperienceRefs??detail.refs:detail.refs)??[];
    detail.componentData={...detail.componentData,experience:{role:detail.role,refs:detail.refs}};
  });
  r.components.on('toolboxes/experience',r.ctx,'datanet/agent-tools',detail=>{detail.view=r.experienceViews.get(detail.ac);});
  r.components.on("toolboxes/experience", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'experience_query', '查询经验线索，默认包括已验证和待审核；status可筛选。待审核不代表建议可靠，不自动加载；不授予权限。', object({
      include_resident: {
        type: 'boolean'
      },
      status: {
        type: 'string',
        enum: ['all', 'verified', 'pending']
      },
      query: str,
      entry_id: str,
      offset: {
        type: 'integer',
        minimum: 0
      },
      kind: {
        type: 'string',
        enum: ['common', 'tool', 'toolbox', 'role', 'node']
      },
      id: str,
      limit: {
        type: 'integer',
        minimum: 1,
        maximum: 10
      }
    }), async p => {
      if (Boolean(p.kind) !== Boolean(p.id)) throw new Error('kind and id must be supplied together');
      const entries = await r.experienceStore.query({
        exclude_ids: p.include_resident || p.entry_id ? [] : [...view.resident],
        status: p.status ?? 'all',
        query: p.query ?? '',
        ids: p.entry_id ? [p.entry_id] : [],
        offset: p.offset ?? 0,
        selectors: p.kind ? [{
          kind: p.kind,
          id: p.id
        }] : [],
        limit: p.limit ?? 6
      });
      for (const e of entries) view.add(e);
      await r.problemChannel.queried(ac, entries);
      return {
        entries
      };
    });
  });
  r.components.on("toolboxes/experience", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'experience_submit', '提交已解决并验证的问题为候选经验；不会自动发布。未解决阻塞使用 datanet_feedback。', object({
      applies: {
        type: 'array',
        minItems: 1,
        maxItems: 12,
        items: object({
          kind: {
            type: 'string',
            enum: ['common', 'tool', 'toolbox', 'role', 'node']
          },
          id: str
        }, ['kind', 'id'])
      },
      trigger: str,
      advice: str,
      evidence: str,
      version: str
    }, ['applies', 'trigger', 'advice', 'evidence', 'version']), async p => {
      r.problemChannel.canSubmit(ac);
      const result = await r.experienceStore.submit(p, actor);
      await r.problemChannel.submitted(ac, result.id);
      return result;
    });
  });
  r.components.on("toolboxes/experience", r.ctx, 'datanet/agent-tools', ({
    ac,
    actor,
    role,
    refs,
    view
  }) => {
    r.registerPrivate(ac, 'experience_review', '仅获授权维护者使用：查看候选、审核发布、合并重复、停用过期经验或set_core调整常加载。推广候选仍须维护者确认；发布前核实证据和版本。', object({
      action: {
        type: 'string',
        enum: ['list', 'publish', 'reject', 'merge', 'retire', 'set_core']
      },
      core: {
        type: 'boolean'
      },
      id: str,
      merge_into: str,
      changes: {
        type: 'object'
      },
      offset: {
        type: 'integer',
        minimum: 0
      },
      status: {
        type: 'string',
        enum: ['pending', 'verified', 'retired', 'rejected', 'merged']
      }
    }, ['action']), async p => {
      if (p.action === 'list') return {
        entries: await r.experienceStore.query({
          status: p.status ?? 'pending',
          offset: p.offset ?? 0,
          limit: 10
        })
      };
      if (!p.id) throw new Error('id required');
      return r.experienceStore.review(p, actor);
    });
  });
  r.components.on("toolboxes/experience", r.ctx, 'datanet/agent-capabilities', async ({
    ac,
    actor,
    role,
    refs
  }) => {
    r.permissions.state(ac);
    let view = r.experienceViews.get(ac);
    if (!view) {
      view = new ExperienceView(r.experienceStore, {
        actor,
        role,
        ids: refs,
        tools: [...r.scopes.get(ac).grant.official.tools, ...r.scopes.get(ac).grant.framework.keys()],
        toolboxes: r.scopes.get(ac).grant.expanded
      });
      await view.startup();
      r.experienceViews.set(ac, view);
      r.components.section("toolboxes/experience", ac, {
        name: 'datanet:experience',
        order: 86,
        interpolate: false,
        text: () => view.render({
          active: Boolean(r.problemChannel.state(ac))
        })
      });
      r.components.on("toolboxes/experience", ac, 'tools/pre-execute', async (exec, next) => {
        const own = r.diagnostics.states.get(ac)?.agent;
        if (!exec.agent || exec.agent === own) await r.loadToolExperience(ac, exec.name);
        return next();
      });
    }
  });
}
export function fallback(r) {
  r.experienceViews = new WeakMap();
  r.experienceStore = {
    query: async () => [],
    read: async () => ({
      entries: [],
      runs: []
    })
  };
  r.loadToolExperience = async () => {};
}
