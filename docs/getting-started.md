# Getting Started

Dugalaxy turns a synthetic-data **template** into endless varied, consistent, validated
samples. This walkthrough mirrors what the tool does when you run it — the tool leads; this
page is the transcript. You won't need to learn the template format to get going.

## 1. Install

```bash
pip install dugalaxy
```

## 2. Run `dugalaxy` — it guides you

```bash
dugalaxy
```

On a real terminal this is an interactive first run. It does two things, in order:

1. **An instant win.** It offers to generate data right now — no model, no key, no config —
   by running the deterministic `quickstart`, then shows you one real sample.
2. **Your own data.** It asks whether you already have a template. If you don't, it offers to
   **build one from a one-line description** (the AI builder, step 4 below).

Each step ends by printing the exact next command. In a script, pipe, or CI — anywhere
without a terminal — `dugalaxy` just prints a short help message and exits, so it never hangs.

## 3. See it work instantly (zero setup)

Whether from the guided flow or directly:

```bash
dugalaxy gen quickstart
```

This writes synthetic user profiles to `./output/quickstart/`. Every field is produced by the
seeded engine — nothing is model-written — so there's nothing else to install. The same seed
always reproduces the same data.

## 4. Make your own from one sentence

Don't want to hand-write YAML? Describe the data and let the builder draft it:

```bash
dugalaxy new "short angry support emails about late refunds, each with an order id and a refund amount"
```

The builder asks a model to write the template, **validates that draft with the real loader**,
and retries with the error if it doesn't load — so you never get a broken file. It saves
`./<slug>.yaml` and prints the next command. Two things to know:

- It's a **starting point**, not a verified dataset — skim the file before a big run.
- If no model is set up, it **starts you from the closest bundled example** instead, so you're
  never blocked. (Set up a model later; see step 6.)

Then generate from it:

```bash
dugalaxy gen <your-template>      # 1 sample first; add --n 50 for more
```

Prefer a blank, fully-commented scaffold to edit by hand instead? Use `dugalaxy init my-dataset`.

## 5. Add model-written prose

Some templates — like the bundled `customer-support` example, whose agent reply is
model-written — need a model:

```bash
dugalaxy gen customer-support --n 5 --seed 42
```

By default this runs against a **local [Ollama](https://ollama.com)** model — free and fully
offline. Install Ollama, then pull a model:

```bash
ollama pull llama3.2
```

If Ollama isn't running, Dugalaxy tells you exactly how to proceed (start it, pick another
provider, or fall back to `dugalaxy gen quickstart`). Before any paid run it shows an estimated
cost and asks you to confirm; an unpriced model is gated until you say yes.

## 6. Use a hosted model (optional)

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

Precedence is **CLI flags > config file > template defaults**. Not sure your setup is right?
Run `dugalaxy doctor` for a plain-words check and the one thing to fix next.

## How it fits together

- **Templates** are resolved in this order: an exact path you pass, then
  `./templates/<name>.yaml` in your working directory, then the examples bundled with the
  package (like `customer-support`). Your own templates always win over bundled ones.
- **Output** goes to the `output_dir` declared in the template. The pre-run plan prints the
  exact location before generation starts, and the summary prints every file it wrote.
- Each sample is written to disk **as it is produced** — nothing accumulates in memory.

Ready to author or fine-tune a template by hand? The [template spec](template-spec.md) is the
full reference — go deeper only when you want to.

## Troubleshooting

- **`Template '<name>' not found`** — pass a path, drop the file in `./templates/`, or use a
  bundled example name (e.g. `customer-support`). The error lists every location it checked.
- **Connection refused / Ollama errors** — Ollama isn't running or the model isn't pulled.
  Start Ollama and run `ollama pull <model>`, or switch to a hosted provider with `--provider`.
- **`API key environment variable '…' is not set`** — export the named variable before
  running; Dugalaxy never reads keys from disk. `dugalaxy doctor` checks this for you.
- **`cost unknown for this model — you may be billed`** — there's no price for that model in
  the built-in table, so the cost cap can't protect you. Set `price_per_1k_input` /
  `price_per_1k_output` in your config to enable the cap, or confirm to proceed anyway.
