"""CLI entrypoint. Commands: dugalaxy gen / init / list / doctor / version, plus the
interactive guided first-run on bare `dugalaxy`.

Wired as the `dugalaxy` console script via pyproject.toml [project.scripts]. The CLI
is the marketing: it should make the magic moment — one command, endless varied,
grounded samples — obvious and fast.
"""

import contextlib
import sys
from collections import Counter
from collections.abc import Callable
from functools import partial
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import IntPrompt

from dugalaxy.authoring import Diagnosis, diagnose
from dugalaxy.config.loader import load_config
from dugalaxy.config.schema import Config
from dugalaxy.cost.cache import ResponseCache
from dugalaxy.cost.estimator import (
    CostEstimate,
    enforce_cap,
    estimate_run_cost,
    estimate_tokens,
    resolve_pricing,
)
from dugalaxy.generator.core import RunResult, generate_dataset
from dugalaxy.generator.grounding import ground_output, requires_model
from dugalaxy.generator.interpolation import to_json
from dugalaxy.providers import build_provider
from dugalaxy.reporting.summary import duplicate_warning
from dugalaxy.scenario import generate_scenario
from dugalaxy.template.discovery import discover_templates
from dugalaxy.template.errors import DugalaxyError
from dugalaxy.template.loader import load_template
from dugalaxy.template.spec import TemplateSpec

from .starter import STARTER_TEMPLATE

app = typer.Typer(
    help="Author a data template once, generate endless realistic samples forever.",
    no_args_is_help=False,
)


def _make_output_encoding_safe() -> None:
    """Degrade un-encodable characters instead of crashing on a legacy console.

    On legacy Windows code pages (e.g. cp1252/cp437) a character the page can't encode
    would otherwise raise UnicodeEncodeError mid-render and abort the command. Switching
    the streams to replace-on-error keeps output flowing (a rare glyph becomes ``?``).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="replace")


_make_output_encoding_safe()
console = Console()
err_console = Console(stderr=True)

# When a generated block does not cap its tokens, assume this many for estimation.
_DEFAULT_OUTPUT_TOKENS = 512

# Where a freshly pip-installed user can learn the format (they have no local repo, so
# these must be URLs). Kept here so the welcome screen and `init` point to the same place.
_REPO_URL = "https://github.com/m2sarah2/dugalaxy"
_TEMPLATE_GUIDE_URL = f"{_REPO_URL}/blob/main/docs/template-spec.md"
_GETTING_STARTED_URL = f"{_REPO_URL}/blob/main/docs/getting-started.md"


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Author a data template once, generate endless realistic samples forever."""
    if ctx.invoked_subcommand is not None:
        return
    # Bare `dugalaxy`: on a real terminal, lead the user through a first win and the
    # next step. Piped/CI/non-interactive gets the short static welcome and exits 0 —
    # never block on a prompt nobody can answer.
    if _is_interactive():
        _guided_first_run()
    else:
        _print_welcome()


def _galaxy_mark() -> str:
    """The galaxy emoji where the terminal can render it, else an ASCII fallback.

    Legacy Windows consoles use a codepage (e.g. cp1252) that cannot encode the
    emoji and would raise on print — so degrade instead of crashing the welcome.
    """
    try:
        "🌌".encode(sys.stdout.encoding or "utf-8")
        return "🌌"
    except (LookupError, UnicodeEncodeError):
        return "*"


def _status_marks() -> tuple[str, str]:
    """The ✓/✗ marks where the terminal can render them, else ASCII fallbacks.

    Legacy Windows consoles (e.g. cp1252) can't encode these glyphs; degrade to
    plain text instead of emitting a replacement ``?`` for every check line.
    """
    try:
        "✓✗".encode(sys.stdout.encoding or "utf-8")
        return "✓", "✗"
    except (LookupError, UnicodeEncodeError):
        return "OK", "X"


def _print_welcome() -> None:
    """Print a friendly branded welcome with the obvious next steps."""
    from dugalaxy import __version__

    body = (
        "[dim]Author a data template once, then generate endless varied, grounded\n"
        "samples. No re-prompting.[/dim]\n\n"
        "[bold]Get started[/bold]\n"
        "  [cyan]dugalaxy gen quickstart[/cyan]         instant demo — no setup needed\n"
        "  [cyan]dugalaxy gen customer-support[/cyan]   model-written chats (needs a provider)\n"
        "  [cyan]dugalaxy init[/cyan]                   scaffold your own template\n"
        "  [cyan]dugalaxy list[/cyan]                   see available templates\n"
        "  [cyan]dugalaxy doctor[/cyan]                 check your setup, fix what's missing\n\n"
        "[bold]Learn[/bold]\n"
        f"  Getting started   [dim]{_GETTING_STARTED_URL}[/dim]\n"
        f"  Template format   [dim]{_TEMPLATE_GUIDE_URL}[/dim]\n"
        f"  Project & docs    [dim]{_REPO_URL}[/dim]"
    )
    console.print(
        Panel(
            body,
            title=f"{_galaxy_mark()}  Dugalaxy  v{__version__}",
            title_align="left",
            border_style="magenta",
            padding=(1, 2),
        )
    )


def _is_interactive() -> bool:
    """True when both stdin and stdout are a real terminal.

    The guided flow asks questions, so it must only run when someone can answer and
    see the result. Piped input, CI, or a redirected stream falls back to the static
    welcome (kept as one helper so tests can flip a single switch).
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


def _guided_first_run() -> None:
    """Walk a first-time user from a zero-setup win to their own data.

    Step 1 is an instant, no-setup win (the deterministic quickstart). Only after the
    win do we ask about their own data — and the "no template yet" branch is where the
    AI builder will live (M3); for now it points at `init`.
    """
    from dugalaxy import __version__

    console.print(
        f"[bold magenta]Dugalaxy[/bold magenta] v{__version__} — let's get you data. "
        "No manual needed.\n"
    )

    if typer.confirm("Want to see it work right now? It needs nothing installed", default=True):
        try:
            _run_quickstart_win()
        except (DugalaxyError, OSError) as exc:
            # This is the very first screen a new user sees — never crash it with a
            # traceback. A DugalaxyError is an expected failure; an OSError covers a
            # cwd we can't write the demo output into (read-only/sandboxed dir).
            err_console.print(
                f"[red]Couldn't run the demo:[/red] {exc}\n"
                "Try again from a writable directory, or run [cyan]dugalaxy doctor[/cyan]."
            )
            return

    if typer.confirm("Do you already have a template?", default=False):
        console.print(
            "Great — run:  [cyan]dugalaxy gen <name-or-path>[/cyan]\n"
            "  Stuck? Run [cyan]dugalaxy doctor[/cyan] to check your setup."
        )
    else:
        _suggest_make_a_template()


def _run_quickstart_win() -> None:
    """Generate the bundled quickstart dataset and show the user one real sample."""
    resolved = _resolve_template_path("quickstart")
    spec = load_template(resolved)
    out_dir = Path(spec.generation.output_dir)
    result = generate_dataset(spec, output_dir=out_dir)

    console.print(
        f"\n[green]Done.[/green] Wrote {result.summary.produced} samples to [bold]{out_dir}[/bold]"
    )
    sample = _first_sample_line(result)
    if sample is not None:
        console.print("[dim]One sample:[/dim]")
        console.print(f"  {sample}")
    console.print(
        "\n[bold]That's real synthetic data, generated locally[/bold] — now let's make YOURS.\n"
    )


def _first_sample_line(result: RunResult) -> str | None:
    """Return the first line of the run's JSONL output, if any was written."""
    for path in result.output_files:
        if path.suffix == ".jsonl":
            try:
                with path.open(encoding="utf-8") as handle:
                    return handle.readline().strip() or None
            except OSError:
                return None
    return None


def _suggest_make_a_template() -> None:
    """Point a user with no template at the fastest way to get one (pre-AI-builder)."""
    console.print(
        "No problem — scaffold one to edit:\n"
        "  [cyan]dugalaxy init my-dataset[/cyan]   then   [cyan]dugalaxy gen my-dataset[/cyan]\n"
        "  See what's available:   [cyan]dugalaxy list[/cyan]\n"
        f"  Template format guide:  [dim]{_TEMPLATE_GUIDE_URL}[/dim]"
    )


@app.command()
def version() -> None:
    """Print the installed Dugalaxy version."""
    from dugalaxy import __version__

    typer.echo(f"dugalaxy {__version__}")


@app.command(name="list")
def list_templates() -> None:
    """List the templates Dugalaxy can find — bundled examples and your own."""
    infos = discover_templates()
    if not infos:
        console.print("No templates found. Run [cyan]dugalaxy init[/cyan] to scaffold one.")
        return
    console.print("[bold]Available templates[/bold]")
    for info in infos:
        console.print(
            f"  [cyan]{info.name}[/cyan]  [dim]({info.source})[/dim]"
            + (f" — {info.description}" if info.description else "")
        )
    console.print("\nRun one with: [cyan]dugalaxy gen <name>[/cyan]")


@app.command()
def doctor(
    provider: Annotated[
        str | None, typer.Option("--provider", help="openai_compatible|anthropic|ollama.")
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model name.")] = None,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Override the endpoint.")
    ] = None,
    api_key_env: Annotated[
        str | None, typer.Option("--api-key-env", help="Env var with the key.")
    ] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Path to config.yaml.")
    ] = None,
) -> None:
    """Check your environment and tell you the one thing to do next."""
    diagnosis = diagnose(
        config_path=config_path,
        overrides={
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key_env": api_key_env,
        },
    )
    _print_diagnosis(diagnosis)


@app.command()
def init(
    name: Annotated[str, typer.Argument(help="Name for the new template (and its slug).")] = (
        "my-dataset"
    ),
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Where to write the file.")
    ] = None,
) -> None:
    """Scaffold a commented, ready-to-run starter template."""
    path = output or Path(f"{name}.yaml")
    if path.exists():
        err_console.print(f"[red]Error:[/red] {path} already exists; refusing to overwrite.")
        raise typer.Exit(1)
    path.write_text(STARTER_TEMPLATE.replace("__NAME__", name), encoding="utf-8")
    console.print(f"[green]Created[/green] {path}")
    console.print(f"Next: [bold]dugalaxy gen {path}[/bold]")
    console.print(
        f"  This template has a model-written turn, so it needs Ollama running "
        f"([bold]ollama pull llama3.2[/bold]) or a provider via [bold]--provider/--model[/bold].\n"
        f"  No setup yet? Try [bold]dugalaxy gen quickstart[/bold] — deterministic, no model "
        f"needed.\n"
        f"  Output is written to [bold]./output/{name}/[/bold].\n"
        f"  Editing the template? The format guide: [dim]{_TEMPLATE_GUIDE_URL}[/dim]"
    )


@app.command()
def gen(
    template: Annotated[
        str | None,
        typer.Argument(help="Template name (in ./templates or bundled) or a path."),
    ] = None,
    n: Annotated[int | None, typer.Option("--n", help="Number of samples.")] = None,
    seed: Annotated[int | None, typer.Option("--seed", help="Run seed.")] = None,
    max_retries: Annotated[
        int | None, typer.Option("--max-retries", help="Retries per sample.")
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Where to write output.")
    ] = None,
    output_format: Annotated[
        list[str] | None, typer.Option("--format", "-f", help="Output format(s): jsonl, yaml.")
    ] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="openai_compatible|anthropic|ollama.")
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="Model name.")] = None,
    base_url: Annotated[
        str | None, typer.Option("--base-url", help="Override the endpoint.")
    ] = None,
    api_key_env: Annotated[
        str | None, typer.Option("--api-key-env", help="Env var with the key.")
    ] = None,
    cost_cap: Annotated[float | None, typer.Option("--cost-cap", help="Hard USD cap.")] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Path to config.yaml.")
    ] = None,
    include_meta: Annotated[
        bool, typer.Option("--include-meta", help="Attach facts+seed.")
    ] = False,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Disable the response cache.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the pre-run confirmation.")
    ] = False,
) -> None:
    """Generate a dataset from a template — the magic moment."""
    try:
        if template is None:
            template = _choose_template()
        resolved = _resolve_template_path(template)
        spec = load_template(resolved)
        config = load_config(
            _resolve_config_path(config_path),
            overrides={
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "api_key_env": api_key_env,
                "cost_cap_usd": cost_cap,
            },
        )

        gen_cfg = spec.generation
        seed_eff = _resolve_seed(seed, gen_cfg.seed)
        retries_eff = max_retries if max_retries is not None else gen_cfg.max_retries
        out_dir = output_dir if output_dir is not None else Path(gen_cfg.output_dir)
        formats = output_format if output_format else list(gen_cfg.output_formats)

        needs_model = requires_model(spec.output)
        provider_obj = build_provider(config) if needs_model else None

        # Safe by default: with no explicit --n, a model-backed run produces a single
        # sample (and says so) rather than firing the template's full batch — a CLI gives
        # no UI friction to catch a forgotten flag, and an accidental large paid/quota run
        # is the worst first experience. Deterministic-only runs are free, so they keep
        # the template's n (variety is the point of the demo).
        n_capped_to_one = n is None and needs_model
        n_eff = 1 if n_capped_to_one else (n if n is not None else gen_cfg.n)

        _print_plan(
            spec,
            config,
            n=n_eff,
            seed=seed_eff,
            needs_model=needs_model,
            out_dir=out_dir,
            formats=formats,
            template_path=resolved,
        )
        if n_capped_to_one:
            console.print(
                f"  [yellow]no --n given:[/yellow] generating 1 sample (this run uses a "
                f"model). Pass [bold]--n {gen_cfg.n}[/bold] for the template's full set."
            )
        estimate = _estimate_cost(spec, config, n=n_eff, seed=seed_eff, needs_model=needs_model)
        _print_estimate(estimate)
        enforce_cap(estimate, config.cost_cap_usd)

        if needs_model and not estimate.free and not yes:
            prompt = (
                "cost unknown for this model — you may be billed. Proceed?"
                if not estimate.priced
                else "Proceed?"
            )
            if not typer.confirm(prompt):
                console.print("Aborted.")
                raise typer.Exit(1)

        cache = None if no_cache else ResponseCache(out_dir / ".cache")
        run = partial(
            generate_dataset,
            spec,
            provider=provider_obj,
            cache=cache,
            n=n_eff,
            seed=seed_eff,
            max_retries=retries_eff,
            output_dir=out_dir,
            output_formats=formats,
            include_meta=include_meta,
        )
        result = _run_with_progress(run, total=n_eff)
        _print_summary(result)
        if result.stopped_early is not None:
            raise typer.Exit(1)
    except DugalaxyError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


# ──────────────────────────── helpers ────────────────────────────


def _print_diagnosis(diagnosis: Diagnosis) -> None:
    """Render the doctor's checks as ✓/✗ lines plus the single next action.

    Always exits 0: ``doctor`` reports health, it does not fail. A missing model is
    an expected state (the zero-setup demo still works), not an error — the
    next-action line carries the signal a script would read.
    """
    ok_mark, bad_mark = _status_marks()
    arrow = "→" if ok_mark == "✓" else "->"
    console.print("[bold]Dugalaxy environment check[/bold]\n")
    for check in diagnosis.checks:
        mark = f"[green]{ok_mark}[/green]" if check.ok else f"[red]{bad_mark}[/red]"
        console.print(f"  {mark} [bold]{check.label}[/bold]: {check.detail}")
        if not check.ok and check.fix:
            console.print(f"      [dim]{arrow} {check.fix}[/dim]")
    console.print(f"\n[bold]Next:[/bold] {diagnosis.next_action}")


def _choose_template() -> str:
    """Interactively pick a template when ``gen`` is run with no argument."""
    infos = discover_templates()
    if not infos:
        raise DugalaxyError(
            "No templates found. Run `dugalaxy init` to scaffold one, or pass a path."
        )
    if not sys.stdin.isatty():
        raise DugalaxyError("No template given. Pass a name or path (see `dugalaxy list`).")

    console.print("[bold]Which template?[/bold]")
    for i, info in enumerate(infos, 1):
        console.print(f"  [bold]{i}[/bold]. [cyan]{info.name}[/cyan] [dim]({info.source})[/dim]")
    choice = IntPrompt.ask("Number", default=1)
    if not 1 <= choice <= len(infos):
        raise DugalaxyError(f"Pick a number between 1 and {len(infos)}.")
    return str(infos[choice - 1].path)


def _resolve_template_path(name: str) -> Path:
    """Resolve a template argument to a file.

    Search order: a direct path, then ``./templates/<name>.yaml`` and ``./<name>.yaml``
    in the working directory (so your own templates always win), then the example
    templates bundled inside the installed package (so ``dugalaxy gen customer-support``
    works straight after ``pip install``, with no repo clone).
    """
    candidates = [Path(name)]
    if not name.endswith((".yaml", ".yml")):
        candidates.append(Path("templates") / f"{name}.yaml")
        candidates.append(Path(f"{name}.yaml"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    if not name.endswith((".yaml", ".yml")):
        bundled = files("dugalaxy") / "templates" / f"{name}.yaml"
        if bundled.is_file():
            return Path(str(bundled))

    looked = ", ".join(str(c) for c in candidates)
    raise DugalaxyError(
        f"Template '{name}' not found. Looked at: {looked}, and the bundled examples."
    )


def _resolve_config_path(explicit: Path | None) -> Path | None:
    """Use the explicit config path, else ./dugalaxy.config.yaml if it exists, else defaults."""
    if explicit is not None:
        return explicit
    default = Path("dugalaxy.config.yaml")
    return default if default.is_file() else None


def _resolve_seed(cli_seed: int | None, template_seed: int | None) -> int:
    if cli_seed is not None:
        return cli_seed
    if template_seed is not None:
        return template_seed
    import random

    return random.randrange(2**31)


def _estimate_cost(
    spec: TemplateSpec, config: Config, *, n: int, seed: int, needs_model: bool
) -> CostEstimate:
    """Estimate run cost from a representative grounded sample (sample 0)."""
    if not needs_model:
        return estimate_run_cost(
            n=n,
            input_tokens_per_sample=0,
            output_tokens_per_sample=0,
            price_per_1k_input=0.0,
            price_per_1k_output=0.0,
            priced=True,
            free=True,
        )

    facts = generate_scenario(spec.scenario, seed=seed, index=0)
    grounded = ground_output(spec.output, facts)

    parts: list[str] = [grounded.system_prompt or ""]
    output_tokens = 0
    for block in grounded.blocks:
        if block.request is None:
            parts.append(block.value if isinstance(block.value, str) else to_json(block.value))
        else:
            parts.append(block.request.instruction)
            output_tokens += block.request.max_tokens or _DEFAULT_OUTPUT_TOKENS

    input_tokens = estimate_tokens("\n".join(parts))
    price_in, price_out, priced = resolve_pricing(config.provider, config.model, config)
    return estimate_run_cost(
        n=n,
        input_tokens_per_sample=input_tokens,
        output_tokens_per_sample=output_tokens,
        price_per_1k_input=price_in,
        price_per_1k_output=price_out,
        priced=priced,
        free=config.provider == "ollama",
    )


def _print_plan(
    spec: TemplateSpec,
    config: Config,
    *,
    n: int,
    seed: int,
    needs_model: bool,
    out_dir: Path,
    formats: list[str],
    template_path: Path,
) -> None:
    console.print(f"[bold]{spec.meta.name}[/bold] — {spec.meta.description}")
    console.print(f"  template: {template_path}")
    target = (
        "deterministic (no model)" if not needs_model else f"{config.provider} / {config.model}"
    )
    console.print(f"  samples: {n}   seed: {seed}   target: {target}")
    console.print(f"  output: {out_dir}   formats: {', '.join(formats)}")
    warning = duplicate_warning(spec.scenario, n)
    if warning:
        console.print(f"  [yellow]warning:[/yellow] {warning}")


def _print_estimate(estimate: CostEstimate) -> None:
    if estimate.free:
        console.print("  estimated cost: [green]free[/green] (local)")
    elif not estimate.priced:
        console.print(
            "  estimated cost: [yellow]unknown[/yellow] — no price for this model; "
            "set price_per_1k_* in config to enable the cost cap."
        )
    else:
        tokens = f"~{estimate.total_input_tokens} in + {estimate.total_output_tokens} out tokens"
        console.print(
            f"  estimated cost: [bold]~${estimate.estimated_cost_usd:.4f}[/bold] "
            f"({tokens}) — approximate"
        )


def _run_with_progress(run: Callable[..., RunResult], *, total: int) -> RunResult:
    """Run generation, showing a progress bar in an interactive terminal.

    A long model-backed run otherwise looks like a frozen terminal. The bar is transient
    (it clears on completion) and is shown only on a real TTY, so piped/CI output stays
    clean and the run summary is the only thing left behind.
    """
    if not console.is_terminal:
        return run()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Generating samples", total=total)
        return run(on_progress=lambda done, _total: progress.update(task, completed=done))


def _print_summary(result: RunResult) -> None:
    summary = result.summary
    if result.stopped_early is not None:
        console.print("\n[bold yellow]Stopped early.[/bold yellow]")
        console.print(f"  reason: {result.stopped_early}")
    else:
        console.print("\n[bold green]Done.[/bold green]")
    console.print(
        f"  produced {summary.produced}/{summary.requested}"
        f"   dropped {summary.dropped}   retries {summary.total_retries}"
    )
    if result.drop_reasons:
        counts = Counter(result.drop_reasons)
        detail = ", ".join(
            f"{reason} (x{n})" if n > 1 else reason for reason, n in counts.most_common()
        )
        console.print(f"  [yellow]dropped because:[/yellow] {detail}")
    console.print(
        f"  diversity: {summary.unique_scenarios} unique scenario combinations "
        f"across the categorical axes ({summary.diversity_ratio:.0%} of produced)"
    )
    for path in result.output_files:
        console.print(f"  wrote {path}")


if __name__ == "__main__":
    app()
