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

## Faker kinds (`type: faker`, the `kind:` field)

A `faker` variable produces a seeded, realistic fake value. Only this curated set of
kinds is supported — a small, named whitelist keeps templates portable and reproducible
(an unknown `kind` is a clear pre-run error listing the valid options). For values outside
this set, use a `choice` variable with your own list.

| Kind              | Produces                                  | Notes |
|-------------------|-------------------------------------------|-------|
| `name`            | A person's full name                      | |
| `email`           | An email address                          | |
| `phone_number`    | A phone number                            | |
| `company`         | A company name                            | |
| `city`            | A city name                               | |
| `country`         | A country name                            | |
| `datetime_recent` | An ISO-8601 UTC timestamp                 | within `days_back` days (default 30) before a fixed anchor; override the window with `days_back:` and the anchor with `anchor:` (ISO-8601) |
| `ipv4`            | An IPv4 address                           | |
| `mac_address`     | A MAC address                             | |
| `domain_name`     | A domain name                             | |
| `hostname`        | A host/workstation name                   | |
| `uuid4`           | A random UUID (v4)                        | |
| `sha256`          | A 64-char hex digest                      | stands in for a file/process hash |
| `file_path`       | A filesystem path                         | |

All kinds are deterministic: the same run seed always yields the same value for a given
variable. Example:

```yaml
city:
  type: faker
  kind: city
opened_at:
  type: faker
  kind: datetime_recent
  days_back: 90
```
