<!-- The one-line positioning below is a PLACEHOLDER — we lock the final version next. -->

# Dugalaxy

**Author a data template once — generate endless varied, consistent, realistic test data forever. No re-prompting.**

Dugalaxy turns the intent behind your synthetic data into a durable, reusable asset. Describe
the *shape* of the data you need once, as a template; then regenerate thousands of varied,
consistent, validated samples with a single command.

> **Status:** Early and actively built in the open by a solo developer. v1 focuses on
> **Template mode**. Expect rapid iteration. Issues and feedback are very welcome.

---

## Why Dugalaxy is not "just an LLM wrapper"

Three ideas, together, make this a *tool* rather than a chat session:

1. **Template as a durable asset.** Author the intent once; regenerate forever with one
   command. No re-explaining your intent to a chatbot every single time.
2. **Deterministic grounding.** The model **never invents the structured facts.** A seeded,
   deterministic engine generates the ground-truth facts of each scenario; those facts are
   templated directly into structured payloads (guaranteed valid) *and* handed to the model as
   ground truth. The model only ever writes free-form prose, conditioned on facts it is given.
3. **Disk-backed, no context bloat.** Every sample is written to disk as it is produced. The
   model's context never accumulates prior output — so generation scales indefinitely at flat
   cost, with no degradation.

---

## Quickstart

```bash
pip install dugalaxy

# scaffold a commented starter template (writes ./my-dataset.yaml)
dugalaxy init

# generate from it — local Ollama by default, so no API key and fully offline
dugalaxy gen my-dataset.yaml

# or run the flagship example from a repo clone, overriding n and seed:
dugalaxy gen security-incident-triage --n 100 --seed 42
```

Before each run Dugalaxy prints what it will do — sample count, seed, target model, an
estimated cost, and a duplicate-risk warning — and asks for confirmation on paid runs. After
the run it reports produced/dropped/retries and a **diversity metric** so variety is provable.

Output is written incrementally as **JSONL** (the lingua franca of LLM eval/fine-tune datasets)
and as a **YAML** dataset envelope. Pick formats with `--format jsonl --format yaml`.

### Bring your own model

Dugalaxy talks to OpenAI-compatible APIs (OpenAI, DeepSeek, Groq, Together, …), Anthropic,
and **local models via Ollama** (fully offline, zero API cost). Which model you use is just
configuration — copy `dugalaxy.config.example.yaml` to `dugalaxy.config.yaml` and edit.

Templates that contain no model-written prose run **fully deterministically — no model, no API
key required.**

---

## Defensive security note

The flagship example template generates **synthetic, defensive SOC / detection-engineering
test data** (e.g. EDR alert triage conversations). All payloads are obviously synthetic and
inert. Dugalaxy is a test-data generator; it does not produce, optimize, or deploy anything
operational.

---

## Documentation

- [Getting started](docs/getting-started.md)
- [Template spec](docs/template-spec.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

[AGPL-3.0-only](LICENSE). Free for any internal use. If you offer Dugalaxy as a hosted or
commercial service, the AGPL requires you to open-source your whole stack. For commercial
licensing that doesn't carry that obligation, open an issue to start a conversation.
