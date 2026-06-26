<p align="center">
  <a href="https://nugalaxy.ai">
    <img src="https://raw.githubusercontent.com/nugalaxy/dugalaxy/main/assets/dugalaxy_banner.png" alt="dugalaxy — powered by nugalaxy.ai" width="820">
  </a>
</p>

# Dugalaxy

**Ask a chatbot for test data and you get five samples that drift, repeat, and contradict each other. Dugalaxy gives you a reusable _template_ instead — describe it once, generate thousands of varied, consistent, validated samples. Offline. Reproducible. No re-prompting.**

Under the hood, a seeded engine invents the ground-truth facts, the model writes only the
prose around them, and every sample is checked and written to disk. Flat cost, reproducible,
thousands of samples from one command — and you don't even have to write the template by hand.

> **Status:** Early and actively built in the open. v1 focuses on **Template mode**.
> Expect rapid iteration. Issues and feedback are very welcome.

---

## Get started in four steps

```bash
# 1. Install
pip install dugalaxy

# 2. Run it with no arguments — it guides you from here
dugalaxy

# 3. See it work instantly (zero setup — no model, no key, no config)
dugalaxy gen quickstart

# 4. Make your own from one sentence
dugalaxy new "short angry support emails about late refunds, each with an order id and a refund amount"
```

That's it. Step 2 walks you through the rest interactively; the steps below are the same
path spelled out, in case you'd rather drive it yourself.

- **`dugalaxy`** — the guided first run. It gives you an instant win, then offers to build
  your own template. (In a script or pipe it just prints help and exits — never hangs.)
- **`dugalaxy gen quickstart`** — fully **deterministic** synthetic profiles. The seeded
  engine writes every field, so it needs no model at all. Real data the second you install.
- **`dugalaxy new "<description>"`** — the AI builder drafts a template from your sentence,
  validates it against the real loader (retrying if needed), and saves `./<slug>.yaml`. With
  no model available it starts you from the closest example instead — you're never blocked.
  The result is a **starting point** to skim, not a verified dataset.
- **`dugalaxy gen <your-template>`** — generate from it (1 sample first; `--n N` for more).
- **`dugalaxy doctor`** — plain-words check of your setup, with the one thing to fix next.

Before each run Dugalaxy prints what it will do — sample count, seed, target model, output
location, an estimated cost, and a duplicate-risk warning — and gates paid runs behind a
confirmation. After it, it reports produced/dropped/retries and a **diversity metric** so
variety is provable. Output is written incrementally as **JSONL** (the lingua franca of LLM
eval/fine-tune datasets) and as a **YAML** dataset envelope; pick with `--format`.

New here? Follow the [getting-started walkthrough](https://github.com/nugalaxy/dugalaxy/blob/main/docs/getting-started.md).

---

## What makes it more than an LLM wrapper

Three ideas, together, make this a *tool* rather than a chat session:

1. **Template as a durable asset.** Author the intent once; regenerate forever with one
   command. No re-explaining yourself to a chatbot every time.
2. **Deterministic grounding.** The model **never invents the structured facts.** A seeded
   engine generates the ground-truth facts of each scenario; those facts are templated into
   structured payloads (guaranteed valid by serialization) *and* handed to the model as
   ground truth. The model only ever writes free-form prose, conditioned on facts it is given.
3. **Disk-backed, no context bloat.** Every sample is written to disk as it is produced. The
   model's context never accumulates prior output — so generation scales indefinitely at flat
   cost, with no degradation.

Want to write or tune a template by hand? The [template spec](https://github.com/nugalaxy/dugalaxy/blob/main/docs/template-spec.md)
is the full reference — but you never *need* to read it to get started.

---

## Bring your own model

Dugalaxy talks to OpenAI-compatible APIs (OpenAI, DeepSeek, Groq, Together, …), Anthropic,
and **local models via Ollama** (fully offline, zero API cost — the default). Using a hosted
model is two small steps:

**1. Put a `dugalaxy.config.yaml` in the directory you run from** (it's read from your current
working directory):

```yaml
provider: openai_compatible
base_url: https://api.openai.com/v1
model: gpt-4o-mini
api_key_env: OPENAI_API_KEY     # the NAME of the env var — never the key itself
cost_cap_usd: 1.00
```

**2. Set the environment variable that holds your key** (it lives only in that terminal
window — API keys are **never read from a file on disk**):

```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"     # Windows PowerShell
```
```bash
export OPENAI_API_KEY="sk-your-key-here"     # macOS / Linux
```

Then run `dugalaxy doctor` to confirm the config, provider, and key are all green. Prefer no
file? Pass `--provider`/`--model`/`--api-key-env` as flags instead. Precedence is
**CLI flags > config file > template defaults**.

Templates that contain no model-written prose run **fully deterministically — no model,
no API key required.**

---

## A note on the data

Everything Dugalaxy produces is **synthetic test data** — names, emails, IDs, and timestamps
are generated by a seeded engine, not drawn from real people or systems. It is meant for
evaluating, fine-tuning, and testing software. The structured facts are guaranteed valid by
serialization; model-written prose is checked **structurally only** (length, fact-presence),
never for semantic correctness.

---

## Documentation

- [Getting started](https://github.com/nugalaxy/dugalaxy/blob/main/docs/getting-started.md)
- [Template spec](https://github.com/nugalaxy/dugalaxy/blob/main/docs/template-spec.md)
- [Changelog](https://github.com/nugalaxy/dugalaxy/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/nugalaxy/dugalaxy/blob/main/CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[AGPL-3.0-only](LICENSE). Free for any internal use. If you offer Dugalaxy as a hosted or
commercial service, the AGPL requires you to open-source your whole stack. For commercial
licensing that doesn't carry that obligation, open an issue to start a conversation.
