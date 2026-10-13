// Official tools and Skills are private to the Agent scope.
const toolRestrictions = new WeakMap();

async function mountOfficialPreset(ac, agent, host, preferredPreset) {
  const presets = host.get('agentPresets');
  if (!presets) return null; // TUI deployments may provide global tools instead.
  let id = presets.composedPreset(ac);
  if (id === undefined) {
    const saved = host.get('sessionProjections')?.stateOf(agent.session, 'agentPreset');
    id = (await presets.mount(ac, preferredPreset ?? saved ?? agent.session.header.agentPreset ?? 'standard')).id;
    if (saved !== id) agent.session.append('agent-preset/selected', { agentPreset: id });
  }
  return id;
}

export function updateCapabilityTools(ac, agent, profile, host, permissions) {
  const previous = toolRestrictions.get(ac);
  previous?.dispose();
  try {
    const known = new Set(host.tools.schemas(agent).map(x => x.name));
    const tools = profile.tools.filter(x => known.has(x));
    // The official registry exempts tools registered in the Agent's own layer.
    const restrictable = host.tools.view(agent).restrictableNames;
    const retained = [...new Set([...(permissions?(previous?.retained??previous?.tools??[]):[]),...tools])];
    const allow = retained.filter(name => restrictable.has(name));
    const dispose = ac.tools.restrict({ allow });
    permissions?.official(ac, profile.tools);
    toolRestrictions.set(ac, { tools, retained, allow, dispose });
    return { tools, unavailableTools: profile.tools.filter(x => !known.has(x)) };
  } catch (error) {
    if (previous) toolRestrictions.set(ac, { tools: previous.tools, retained: previous.retained, allow: previous.allow, dispose: ac.tools.restrict({ allow: previous.allow }) });
    else toolRestrictions.delete(ac);
    throw error;
  }
}

export async function applyCapabilities(ac, agent, profile, host, preferredPreset, permissions) {
  const officialPreset = await mountOfficialPreset(ac, agent, host, preferredPreset);
  const officialTools = updateCapabilityTools(ac, agent, profile, host, permissions);
  const initialSkills=await host.skills.list({cwd:agent.session.header.cwd,scope:agent});
  const explicitSkills=new Set(profile.skills==='*'?initialSkills.map(x=>x.name):profile.skills);
  const providerGrants=new Map(initialSkills.filter(x=>(profile.skillProviders??[]).includes(x.provider)).map(x=>[x.name,x.provider]));
  const selectedSkills=[...new Set([...explicitSkills,...providerGrants.keys()])];
  const permitted = name => explicitSkills.has(name)||providerGrants.has(name);
  let currentProviders=new Map(initialSkills.map(x=>[x.name,x.provider]));
  ac.tools.guard(exec => {
    if(exec.agent?.ctx&&exec.agent.ctx!==ac)return;
    if(exec.name!=='skill')return;
    const name=exec.arguments?.name;
    if(!permitted(name))return `Skill is not granted to this Agent: ${name}`;
    if(providerGrants.has(name)&&!explicitSkills.has(name)){
      if(currentProviders.get(name)!==providerGrants.get(name))return `Skill provider changed: ${name}`;
    }
  });

  const masked = new Set();
  async function maskSkills(signal) {
    
    const skills = await host.skills.list({ cwd: agent.session.header.cwd, scope: agent, signal });
    currentProviders=new Map(skills.map(x=>[x.name,x.provider]));
    for (const skill of skills) {
      if ((explicitSkills.has(skill.name)||(providerGrants.get(skill.name)!==undefined&&providerGrants.get(skill.name)===skill.provider)) || masked.has(skill.name)) continue;
      // Scoped non-invocable entries shadow host entries in the official registry.
      // This also blocks /skill-name injection, not just model tool calls.
      ac.get('skills').register({ name: skill.name, description: 'Not granted to this Agent',
        source: 'runtime', content: '', invocation: { modelInvocable: false, userInvocable: false } });
      masked.add(skill.name);
    }
  }
  await maskSkills();
  ac.on('agent/pre-step', async ({ signal }, next) => { await maskSkills(signal); return next(); });
  return { ...officialTools, skills: selectedSkills, officialPreset };
}
