"""Runtime configuration: provider/model/keys/caps, loaded from dugalaxy.config.yaml and CLI flags.

Owns the precedence rule: CLI flags > dugalaxy.config.yaml > template defaults.
Never reads secrets from disk; resolves API keys from environment variable NAMES only.
"""
