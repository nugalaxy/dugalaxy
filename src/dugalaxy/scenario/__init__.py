"""Deterministic, seeded scenario generation engine.

Samples the variation axes of a scenario BEFORE any model call. The model never
invents these facts. Per-sample seed derived from (global_seed, sample_index);
per-variable RNG from (sample_seed, variable_name) so faker is reproducible too.
"""
