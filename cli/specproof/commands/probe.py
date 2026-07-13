"""specproof probe — Run LLM provider capability probe."""

import asyncio
import json
import sys

import click

from providers.capability_probe import CapabilityProbe


@click.command("probe")
@click.option(
    "--base-url",
    envvar="LLM_BASE_URL",
    required=True,
    help="OpenAI-compatible API base URL",
)
@click.option(
    "--api-key",
    envvar="LLM_API_KEY",
    required=True,
    help="API key (never logged)",
)
@click.option(
    "--model",
    envvar="LLM_MODEL",
    default="deepseek-v4-pro",
    help="Model name to probe",
)
@click.option("--timeout", default=60.0, help="Per-request timeout in seconds")
@click.option("--json-output", "json_out", is_flag=True, help="Output raw JSON")
def probe(base_url: str, api_key: str, model: str, timeout: float, json_out: bool) -> None:
    """Probe an OpenAI-compatible LLM gateway for 10 capability dimensions.

    Results are printed to stdout. Use --json-output for machine-readable output.
    """
    if api_key == "replace_me":
        click.echo("ERROR: LLM_API_KEY is 'replace_me'. Set a real API key.", err=True)
        sys.exit(1)

    click.echo(f"Probing {base_url} with model {model}...")
    click.echo(f"API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
    click.echo()

    probe_obj = CapabilityProbe(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
    )
    result = asyncio.run(probe_obj.run())

    if json_out:
        click.echo(
            json.dumps(
                {
                    "provider": result.provider,
                    "base_url": result.base_url,
                    "model": result.model,
                    "capabilities": result.capabilities,
                    "limits": result.limits,
                    "errors": result.errors,
                    "probed_at": result.probed_at,
                },
                indent=2,
            )
        )
    else:
        click.echo(result.summary())

    passed = sum(1 for v in result.capabilities.values() if v)
    total = len(result.capabilities)
    if passed == total:
        click.echo(f"\nAll {total} capabilities passed.")
    else:
        click.echo(f"\n{passed}/{total} capabilities passed. See errors above.")
        sys.exit(1)
