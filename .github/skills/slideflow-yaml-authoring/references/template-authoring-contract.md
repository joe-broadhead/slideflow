# Template Authoring Contract

Template files must include:

- `name`
- `description`
- `version`
- `parameters[]`
- `template`

Parameter fields:

- `name`
- `type`
- `required` (default true)
- `default` (optional)
- `description`

Required parameter enforcement is strict. Missing required params are runtime errors.

Template precedence order:

1. `template_paths` from config
2. `./templates`
3. `~/.slideflow/templates`
4. packaged built-ins

Local templates override built-ins when names collide.
