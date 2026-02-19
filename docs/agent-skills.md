# Agent Skills

SlideFlow includes an Open Skill standard artifact for agentic YAML authoring and
chart configuration guidance.

## Included skill

- `.github/skills/slideflow-yaml-authoring/SKILL.md`

This skill teaches agents to:

- generate valid SlideFlow YAML contracts
- choose chart strategy (`template` vs `plotly_go` vs `custom`)
- map Plotly graph object parameters safely
- apply a deterministic gotchas checklist before final output
- preserve compatibility policy constraints
- validate generated configs before build

## Skill package layout

```text
.github/skills/slideflow-yaml-authoring/
  SKILL.md
  references/
    config-schema-cheatsheet.md
    template-authoring-contract.md
    plotly-parameter-lookup.md
    gotchas.md
  assets/
    snippets/
      connectors.yml
      replacements.yml
      charts.yml
  scripts/
    generate_plotly_reference_index.py
```

## Usage model

1. Install/load the skill in your agent runtime.
2. Ask the agent for a config in terms of intent, data source, and output slide goals.
3. Run:

```bash
slideflow validate config.yml
slideflow build config.yml --dry-run
```

4. Iterate until `validate` + dry-run are clean, then render for real.

## Guardrails

The skill is designed to enforce:

- no feature removals or deprecations
- additive behavior only unless bug/security fix
- deterministic template parameter contracts
- compatibility-safe YAML output
