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
      values:
        - "Nimbus CLI"
        - "Nimbus Cloud"
        - "Nimbus Desktop"

    issue:
      type: weighted_choice            # pick one, with weights (some issues are commoner)
      values:
        login: 0.5
        billing: 0.3
        crashes: 0.2

    ticket_number:
      type: range                      # integer, inclusive on both ends
      min: 1000
      max: 9999

    customer:
      type: faker                      # seeded realistic value (kinds: docs/template-spec.md)
      kind: name

    ticket_id:
      type: computed                   # build a string from other variables
      value: "TICKET-{{ scenario.ticket_number }}"

    ticket:
      type: object                     # a structured map — serialized to VALID JSON for you
      value:                           # (never paste values into a JSON string yourself)
        ticket_id: "{{ scenario.ticket_id }}"
        customer: "{{ scenario.customer }}"
        product: "{{ scenario.product }}"
        category: "{{ scenario.issue }}"

output:
  type: conversation
  # The structured record is the agent's ground truth — the ticket it would see in
  # the support tool. The customer never sends JSON; they just talk (the turn below).
  system_prompt: |
    You are a friendly, concise support agent for {{ scenario.product }}.
    Use the ticket record below as ground truth; do not contradict it. Greet the
    customer by name and cite the ticket id.
    Ticket record:
    ```json
    {{ scenario.ticket | json(indent=2) }}
    ```
  turns:
    - role: user
      content:
        type: fixed                    # the engine fills this; the model never writes it
        value: |
          Hi, I'm {{ scenario.customer }}. I'm using {{ scenario.product }} and I'm
          having trouble with {{ scenario.issue }}. Could you help me out? Thanks!

    - role: agent                      # 'agent' (not 'assistant') — matches common seeders
      content:
        type: generated                # the MODEL writes this, grounded by the record above
        instruction: |
          Acknowledge ticket {{ scenario.ticket_id }} by name and help {{ scenario.customer }}
          with their {{ scenario.issue }} issue on {{ scenario.product }}. Keep it under
          6 sentences.
        max_tokens: 400
        validation:                    # structural checks only — never semantic
          min_length: 40
          must_mention:
            - "{{ scenario.ticket_id }}"

generation:
  n: 10
  seed: 42
  max_retries: 3
  output_dir: "./output/__NAME__"
  output_formats:
    - jsonl
    - yaml
"""
