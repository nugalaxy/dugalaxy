# Template Spec

A Dugalaxy template is a YAML file with **four top-level sections**. Author it once;
generate endless varied, consistent samples.

```yaml
meta:        # identity: name, description, version
scenario:    # the variables that vary per sample (the "dice")
output:      # the SHAPE of each sample (see "Output shapes" below)
generation:  # run controls: how many, what seed, where to write
```

Model/provider settings (provider, model, api_key_env, base_url, cost cap) are **not** in
the template — they live in `dugalaxy.config.yaml` or CLI flags. Precedence:
**CLI flags > config file > template defaults.**

---

## Output shapes — read this first

`output.type` is the one choice that confuses everyone. There are exactly **two** shapes,
and they have **different structures**:

| You want…                                   | Use            | Structure                          |
|---------------------------------------------|----------------|------------------------------------|
| A back-and-forth (user/agent messages)      | `conversation` | a list of **`turns:`**             |
| One standalone artifact per sample          | `document`     | a single **`content:`** block      |

> **The #1 mistake:** putting `turns:` under a `document`, or a lone `content:` under a
> `conversation`. They are not interchangeable. A `document` has **no turns and no roles** —
> it is one thing. A `conversation` is a sequence of role-labelled turns.

### `conversation` — a dialogue

```yaml
output:
  type: conversation
  system_prompt: |              # optional: the model's ground-truth briefing
    You are a support agent for {{ scenario.product }}. Use this record as truth:
    ```json
    {{ scenario.account_record | json(indent=2) }}
    ```
  turns:                         # a LIST; each item has a role + a content block
    - role: user
      content:
        type: fixed              # the engine fills this turn (no model)
        value: "Hi, I'm {{ scenario.customer }} and I need help with {{ scenario.issue }}."
    - role: agent                # 'agent' or 'assistant' — roles are free-form
      content:
        type: generated          # the MODEL writes this turn
        instruction: "Reply to {{ scenario.customer }}; cite {{ scenario.ticket_id }}."
        max_tokens: 600
```

### `document` — one artifact

```yaml
output:
  type: document
  content:                       # a SINGLE block — no turns, no roles
    type: generated              # or 'fixed'
    instruction: "Write one realistic support note for {{ scenario.customer }}."
    max_tokens: 200
```

---

## Content blocks (`content.type`)

Every `content:` block — whether inside a turn or a document — is one of two kinds:

- **`fixed`** — the engine fills it; the model never writes it. `value:` is a string
  (interpolated) **or** a structured map (serialized to valid JSON/YAML for you).
- **`generated`** — the model writes it, grounded by the system prompt. Optional
  **structural** validation only:
  - `min_length`, `max_length` — character bounds
  - `must_mention: [ ... ]` — strings (often `{{ scenario.x }}`) that must appear
  - `must_not_contain: [ ... ]` — strings that must not appear

  Validation is structural, never semantic — it checks shape, not truthfulness.

A template with **no `generated` block** is a *deterministic-only* run: no model, no API
key, no cost (e.g. the bundled `quickstart`).

---

## Scenario variables

Each entry under `scenario.variables` is one variable with its own `type`:

**Primitives** (generate a value directly):
- `choice` — pick one from `values:` (a list), uniformly.
- `weighted_choice` — pick one from `values:` (a map of value → weight).
- `range` — a random integer in `[min, max]`, inclusive.
- `sequence` — an incrementing counter (`start:`, `step:`); independent of the seed.
- `faker` — a seeded realistic value; see **Faker kinds** below.

**Composites** (build on other variables, referenced as `{{ scenario.other_var }}`):
- `computed` — a string built by interpolating other variables (`value: "TICKET-{{ scenario.num }}"`).
- `object` — a structured map whose leaves interpolate other variables; the engine
  **serializes it to valid JSON** (use the `| json` filter to embed it in prose). Author
  structured payloads this way — never hand-type JSON, so a quote or newline can't corrupt it.

References resolve in dependency order; a missing reference or a cycle is a clear pre-run
error. Filters available: `| json(indent=N)`.

---

## `generation`

```yaml
generation:
  n: 100                         # how many samples (CLI --n overrides; see note)
  seed: 42                       # run seed; omit for a random (printed) seed
  max_retries: 3                 # per-sample retries on a failed validation
  output_dir: "./output/my-set"
  output_formats: [jsonl, yaml]  # jsonl, yaml, or both
```

> **Note:** running `dugalaxy gen` on a model-backed template **without `--n`** produces a
> single sample (and says so), so a forgotten flag never fires a large paid run. Pass
> `--n N` for the full set. Deterministic-only runs honor the template's `n`.

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
