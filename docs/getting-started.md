# Getting Started

> Fills in as the build progresses.

## Install

```bash
pip install dugalaxy
```

## Configure a model (optional)

Copy the example config and edit it:

```bash
cp dugalaxy.config.example.yaml dugalaxy.config.yaml
```

Set your key in the environment (the config only names the variable):

```bash
cp .env.example .env   # then edit .env
```

Templates with no model-written prose need no model and no key.

## Generate

```bash
dugalaxy gen security-incident-triage --n 500 --seed 42
```
