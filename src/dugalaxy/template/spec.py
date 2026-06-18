"""Pydantic data model for the template spec (meta, scenario, output, generation)."""

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ──────────────────────────── Scenario variable types ────────────────────────


class ChoiceVar(BaseModel):
    """Pick one value uniformly at random from a flat list."""

    type: Literal["choice"]
    values: list[str]


class WeightedChoiceVar(BaseModel):
    """Pick one value with weighted probabilities; weights need not sum to 1."""

    type: Literal["weighted_choice"]
    values: dict[str, float]

    @field_validator("values")
    @classmethod
    def weights_must_be_positive(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("weighted_choice must have at least one value")
        if any(w <= 0 for w in v.values()):
            raise ValueError("all weights in weighted_choice must be positive")
        return v


class RangeVar(BaseModel):
    """Uniform random integer in [min, max] inclusive."""

    type: Literal["range"]
    min: int
    max: int

    @model_validator(mode="after")
    def min_le_max(self) -> "RangeVar":
        if self.min > self.max:
            raise ValueError(f"range min ({self.min}) must be <= max ({self.max})")
        return self


class SequenceVar(BaseModel):
    """Incrementing counter per sample (useful for incident IDs etc.)."""

    type: Literal["sequence"]
    start: int = 1
    step: int = 1


class FakerVar(BaseModel):
    """Seeded realistic fake value (datetime, IP, name, …).

    Extra kwargs (e.g. ``days_back``) are passed through to the faker provider.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["faker"]
    kind: str


class ComputedVar(BaseModel):
    """String built by interpolating other scenario variables with ``{{ scenario.x }}``."""

    type: Literal["computed"]
    value: str


class ObjectVar(BaseModel):
    """Structured map whose leaf values interpolate other variables.

    The engine serializes this map to JSON, guaranteeing validity regardless of
    what characters appear in the interpolated values.
    """

    type: Literal["object"]
    value: dict[str, Any]


VariableSpec: TypeAlias = Annotated[
    ChoiceVar | WeightedChoiceVar | RangeVar | SequenceVar | FakerVar | ComputedVar | ObjectVar,
    Field(discriminator="type"),
]


# ──────────────────────────── Content blocks ─────────────────────────────────


class FixedContent(BaseModel):
    """Engine fills this block; the model never writes it.

    ``value`` may be a string (interpolated as-is) or a structured map
    (serialized by the engine → guaranteed valid JSON/YAML).
    """

    type: Literal["fixed"]
    value: str | dict[str, Any]


class ValidationSpec(BaseModel):
    """Structural-only validation for generated content (not semantic)."""

    min_length: int | None = None
    max_length: int | None = None
    must_mention: list[str] = Field(default_factory=list)
    must_not_contain: list[str] = Field(default_factory=list)


class GeneratedContent(BaseModel):
    """Model writes this block, grounded by the system prompt."""

    type: Literal["generated"]
    instruction: str
    max_tokens: int | None = None
    validation: ValidationSpec | None = None


ContentSpec: TypeAlias = Annotated[
    FixedContent | GeneratedContent,
    Field(discriminator="type"),
]


# ──────────────────────────── Output shapes ──────────────────────────────────


class Turn(BaseModel):
    """One turn in a conversation: a role and its content."""

    role: str
    content: ContentSpec


class ConversationOutput(BaseModel):
    """An ordered sequence of turns (v1: single user+agent pair)."""

    type: Literal["conversation"]
    system_prompt: str | None = None
    turns: list[Turn]


class DocumentOutput(BaseModel):
    """A single artifact per sample (structured data or prose)."""

    type: Literal["document"]
    content: ContentSpec


OutputSpec: TypeAlias = Annotated[
    ConversationOutput | DocumentOutput,
    Field(discriminator="type"),
]


# ──────────────────────────── Top-level spec ─────────────────────────────────


class Meta(BaseModel):
    """Template identity — used for naming output files and datasets."""

    name: str
    description: str
    version: str = "1.0"
    dataset_name: str | None = None


class ScenarioSpec(BaseModel):
    """All scenario variables, resolved in dependency order at generation time."""

    variables: dict[str, VariableSpec]


class GenerationConfig(BaseModel):
    """Data-generation controls (sample count, seed, retries, output location)."""

    n: int = 1
    seed: int | None = None
    max_retries: int = 3
    output_dir: str = "./output"
    output_formats: list[str] = Field(default_factory=lambda: ["jsonl"])


class TemplateSpec(BaseModel):
    """The complete, validated template — parsed from a YAML file by ``load_template``."""

    meta: Meta
    scenario: ScenarioSpec
    output: OutputSpec
    generation: GenerationConfig
