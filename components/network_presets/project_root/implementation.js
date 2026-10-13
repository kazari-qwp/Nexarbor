export function install(r) {
  r.components.on('network_presets/project_root', r.ctx, 'datanet/root-role', ({
    agent,
    prompt
  }) => {
    if (prompt) r.components.section('network_presets/project_root', agent.ctx, {
      name: 'datanet:root',
      order: 90,
      interpolate: false,
      text: prompt
    });
  });
}
