"""The commented starter template scaffolded by `dugalaxy init`.

Kept as a string constant (with a ``__NAME__`` placeholder) so it ships in the
wheel with no package-data wiring. It is a complete, valid, runnable template that
exercises every core idea: primitives, a computed string, a serialized object, a
fixed turn, and a grounded generated turn.
"""

STARTER_TEMPLATE = """\
# Dugalaxy template — created by `dugalaxy init`.
#
# Author the SHAPE of your data once; generate endless varied, consistent samples.
# Run it with:   dugalaxy gen __NAME__.yaml
#
# Provider/model settings are NOT in this file — they live in dugalaxy.config.yaml
# or CLI flags (e.g. --provider, --model). By default this runs against local Ollama.

meta:
  name: __NAME__
  description: "Example: customer-support conversations"
  version: "1.0"

scenario:
  # Every variable is generated deterministically from the run seed, so the same
  # seed always reproduces the same facts.
  variables:
    product:
      type: choice                     # pick one, uniformly
      values: ["Nimbus CLI", "Nimbus Cloud", "Nimbus Desktop"]

    issue:
      type: weighted_choice            # pick one, with weights (some issues are commoner)
      values: { login: 0.5, billing: 0.3, crash: 0.2 }

    ticket_number:
      type: range                      # integer, inclusive on both ends
      min: 1000
      max: 9999

    customer:
      type: faker                      # seeded realistic value (see docs for the kinds)
      kind: name

    ticket_id:
      type: computed                   # build a string from other variables
      value: "TICKET-{{ scenario.ticket_number }}"

    payload:
      type: object                     # a structured map — serialized to VALID JSON for you
      value:                           # (never paste values into a JSON string yourself)
        ticket_id: "{{ scenario.ticket_id }}"
        product: "{{ scenario.product }}"
        category: "{{ scenario.issue }}"

output:
  type: conversation
  system_prompt: |
    You are a friendly support agent for {{ scenario.product }}.
    Be concise and helpful. Ground truth (do not contradict):
      ticket:  {{ scenario.ticket_id }}
      product: {{ scenario.product }}
      issue:   {{ scenario.issue }}
  turns:
    - role: user
      content:
        type: fixed                    # the engine fills this; the model never writes it
        value: |
          Hi, I'm {{ scenario.customer }} with a {{ scenario.issue }} issue on
          {{ scenario.product }}. Here is my ticket:
          ```json
          {{ scenario.payload | json(indent=2) }}
          ```
          Can you help?

    - role: agent                      # 'agent' (not 'assistant') — matches common seeders
      content:
        type: generated                # the MODEL writes this, grounded by the facts above
        instruction: |
          Acknowledge ticket {{ scenario.ticket_id }} and help with the
          {{ scenario.issue }} issue on {{ scenario.product }}. Keep it under 6 sentences.
        max_tokens: 400
        validation:                    # structural checks only — never semantic
          min_length: 40
          must_mention: ["{{ scenario.ticket_id }}"]

generation:
  n: 10
  seed: 42
  max_retries: 3
  output_dir: "./output/__NAME__"
  output_formats: [jsonl, yaml]
"""
