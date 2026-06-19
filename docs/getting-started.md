# Getting Started

Dugalaxy turns a synthetic-data **template** into endless varied, consistent, validated
samples. The whole loop is: pick (or write) a template → run `dugalaxy gen` → read the
output it writes to disk.

## Install

```bash
pip install dugalaxy
```

## Your first run (zero setup)

The package ships a fully **deterministic** example called `quickstart`, so you can generate
real data the instant you install — no model, no API key, no config:

```bash
dugalaxy gen quickstart
```

It writes synthetic user profiles to `./output/quickstart/`. Because every field is produced
by the seeded engine (nothing is model-written), there's nothing else to install.

## Adding model-written prose

When you want conversational data — like the bundled `customer-support` example, whose agent
reply is written by a model — you need a model:

```bash
dugalaxy gen customer-support --n 5 --seed 42
```

By default this runs against a **local [Ollama](https://ollama.com)** model — free and fully
offline. Install Ollama, then pull a model:

```bash
ollama pull llama3.2
```

If Ollama isn't running, Dugalaxy tells you exactly how to proceed (start it, pick another
provider, or fall back to `dugalaxy gen quickstart`).

## The loop: template → gen → output

- **Templates** are resolved in this order: an exact path you pass, then
  `./templates/<name>.yaml` in your working directory, then the examples bundled with the
  package (like `customer-support`). Your own templates always win over bundled ones.
- **Output** is written to the `output_dir` declared in the template. The `customer-support`
  example writes to `./output/customer-support/`. The pre-run plan prints the exact location
  before generation starts, and the summary prints every file it wrote.
- Each sample is written to disk **as it is produced** — nothing accumulates in memory.

Scaffold your own template with:

```bash
dugalaxy init my-dataset      # writes ./my-dataset.yaml, fully commented
dugalaxy gen my-dataset.yaml
```

## Configure a hosted model (optional)

To use a hosted API instead of Ollama, either pass flags
(`--provider openai_compatible --model gpt-4o-mini --api-key-env OPENAI_API_KEY`) or use a
config file:

```bash
cp dugalaxy.config.example.yaml dugalaxy.config.yaml   # then edit it
```

API keys are **only ever read from the named environment variable** — never from a file on
disk. Set it in your shell (or a `.env` you export):

```bash
cp .env.example .env   # then edit .env
```

Precedence is **CLI flags > config file > template defaults**.

## Troubleshooting

- **`Template '<name>' not found`** — pass a path, drop the file in `./templates/`, or use a
  bundled example name (e.g. `customer-support`). The error lists every location it checked.
- **Connection refused / Ollama errors** — Ollama isn't running or the model isn't pulled.
  Start Ollama and run `ollama pull <model>`, or switch to a hosted provider with `--provider`.
- **`API key environment variable '…' is not set`** — export the named variable before
  running; Dugalaxy never reads keys from disk.
- **`cost unknown for this model — you may be billed`** — there's no price for that model in
  the built-in table, so the cost cap can't protect you. Set `price_per_1k_input` /
  `price_per_1k_output` in your config to enable the cap, or confirm to proceed anyway.
