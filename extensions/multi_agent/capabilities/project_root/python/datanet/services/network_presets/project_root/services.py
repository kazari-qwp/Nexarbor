def register(services):
    package=services.catalog['capabilities/project_root']['directory']/'python/resources/package.json'
    services.root_packages['project_root']=package
