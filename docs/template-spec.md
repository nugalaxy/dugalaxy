# Template Spec

> The full, public reference for the Dugalaxy template format will be published here.
> (Working design is maintained privately during v1 build.)

Summary of the format vocabulary:

- `meta`: name, description, version
- `scenario.variables.<name>.type`: choice | weighted_choice | range | sequence | faker
  (primitives); computed | object (composites)
- `output.type`: conversation | document
- `content.type`: fixed | generated
- filters: `| json(indent=N)`
- `generation`: n, seed, max_retries, output_dir, output_formats
- config (separate file): provider, model, base_url, api_key_env, cost_cap_usd
