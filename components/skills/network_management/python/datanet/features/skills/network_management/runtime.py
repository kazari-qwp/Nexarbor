from datanet.core.application import Component


class Plugin(Component):
    def install(self):
        self.package = self.r.resource(self.id, 'resources/package.json', json_data=True)
        self.on('agent/bound', self.bound)
        self.on('tool/definition', self.definition)

    def definition(self, e):
        if e['name'] == 'datanet_skill':
            e['spec']['parameters']['properties']['name']['enum'] = self.r.state(e['actor'])['grant']['framework'].get('datanet_skill', {}).get('skills', [])

    def bound(self, e):
        for skill in self.r.backend.agents[e['actor']].get('loadedSkills', []):
            self.enable(e['actor'], skill, False)

    def management_guide(self, actor):
        added = self.r.load(actor, 'network_management', self.r.resource(self.id, 'resources/AGENTS.md'))
        experience = self.r.plugins.get('toolboxes/experience')
        if added and experience and actor in experience.views:
            for entry in experience.query(dict(selectors=[dict(kind='toolbox', id='network_management')], status='verified', core_only=True, limit=10)):
                experience.add(actor, entry, True)
        return added

    def enable(self, actor, name, persist=True):
        state = self.r.state(actor)
        allowed = state['grant']['framework'].get('datanet_skill', {}).get('skills', [])
        if name != self.package['id'] or name not in allowed:
            raise PermissionError('Skill is not granted to this Agent')
        loaded = state.setdefault('loaded_skills', set())
        before = name in loaded
        if not before:
            grant = self.r.resolve(list(dict.fromkeys(state['grant']['names'] + self.package['toolboxes'])), role='discussion' if self.r.backend.agents[actor]['kind'] == 'discussion' else state['role'])
            # This capability skill declares only DataNet tools.
            state['grant'] = grant
            loaded.add(name)
            self.r.emit('capabilities/changed', actor=actor)
            self.r.refresh(actor)
        added = False
        if persist:
            content = self.r.resource(self.id, 'resources/' + self.package['entry'])
            for reference in self.package['references']:
                if reference != 'AGENTS.md':
                    content += '\n## 参考：' + reference + '\n' + self.r.resource(self.id, 'resources/' + reference)
            added = self.r.load(actor, 'skill:' + name, content)
            self.management_guide(actor)
            self.r.rpc('agent_progress', target=actor, loadedSkills=list(loaded))
        return dict(name=name, loaded=True, already_loaded=before, instructions_added=added, toolboxes=self.package['toolboxes'], references=self.package['references'])

    def tool_datanet_skill(self, actor, p):
        allowed = self.r.state(actor)['grant']['framework'].get('datanet_skill', {}).get('skills', [])
        if p['action'] == 'list':
            return dict(skills=[dict(id=id, description=self.package['description'], loaded=id in self.r.state(actor).get('loaded_skills', set())) for id in allowed if id == self.package['id']])
        if p.get('name') not in allowed:
            raise PermissionError('Skill is not granted to this Agent')
        if p['action'] == 'load':
            return self.enable(actor, p['name'])
        if p['name'] not in self.r.state(actor).get('loaded_skills', set()):
            raise ValueError('Load this Skill first')
        if p.get('reference') not in self.package['references']:
            raise ValueError('Unknown Skill reference')
        reference = p['reference']
        return dict(name=p['name'], reference=reference, instructions_added=self.r.load(actor, 'network_management' if reference == 'AGENTS.md' else 'skill:' + p['name'] + ':' + reference, self.r.resource(self.id, 'resources/' + reference)))
