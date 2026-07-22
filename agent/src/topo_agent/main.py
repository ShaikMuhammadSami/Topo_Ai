from __future__ import annotations

import json
import logging
import sys

import typer
from rich.console import Console
from rich.table import Table

from topo_agent import __version__
from topo_agent.buffer import (
    SnapshotBuffer,
)
from topo_agent.client import (
    AgentApiClient,
    AgentClientError,
)
from topo_agent.collector import (
    KubernetesCollector,
)
from topo_agent.config import (
    AgentConfig,
    buffer_directory,
    config_path,
    credentials_path,
    load_agent_token,
    load_config,
    save_config,
    store_agent_token,
)
from topo_agent.runner import (
    AgentRunner,
)


app = typer.Typer(
    name="topo-agent",
    help=(
        "Topo AI infrastructure "
        "discovery agent."
    ),
    no_args_is_help=True,
)

console = Console()


def _configure_logging(
    verbose: bool,
) -> None:
    logging.basicConfig(
        level=(
            logging.DEBUG
            if verbose
            else logging.INFO
        ),
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )


def _client(
    config: AgentConfig,
    token: str | None,
) -> AgentApiClient:
    return AgentApiClient(
        backend_url=(
            config.backend_url
        ),
        token=token,
        timeout_seconds=(
            config.timeout_seconds
        ),
        verify_tls=(
            config.verify_tls
        ),
        max_retries=(
            config.max_retries
        ),
        retry_backoff_seconds=(
            config
            .retry_backoff_seconds
        ),
    )


def _runtime() -> tuple[
    AgentConfig,
    AgentApiClient,
    KubernetesCollector,
    SnapshotBuffer,
]:
    config = load_config()

    token = load_agent_token()

    if not token:
        raise typer.BadParameter(
            "The agent is not enrolled. "
            "Run 'topo-agent enroll'."
        )

    client = _client(
        config,
        token,
    )

    collector = KubernetesCollector(
        config
    )

    buffer = SnapshotBuffer(
        buffer_directory(),
        max_items=(
            config.max_buffer_items
        ),
    )

    return (
        config,
        client,
        collector,
        buffer,
    )


@app.command("version")
def version() -> None:
    typer.echo(
        f"topo-agent {__version__}"
    )


@app.command("enroll")
def enroll(
    server: str = typer.Option(
        "http://127.0.0.1:8000",
        "--server",
    ),
    name: str = typer.Option(
        "topo-agent",
        "--name",
    ),
    cluster_name: str = typer.Option(
        "docker-desktop",
        "--cluster",
    ),
    environment: str | None = typer.Option(
        None,
        "--environment",
    ),
    namespace: list[str] = typer.Option(
        [],
        "--namespace",
        "-n",
    ),
    kube_context: str | None = typer.Option(
        None,
        "--kube-context",
    ),
    enrollment_token: str | None = typer.Option(
        None,
        "--token",
    ),
    token_stdin: bool = typer.Option(
        False,
        "--token-stdin",
    ),
    collection_interval: int = typer.Option(
        300,
        "--collection-interval",
        min=30,
    ),
    heartbeat_interval: int = typer.Option(
        30,
        "--heartbeat-interval",
        min=10,
    ),
    insecure: bool = typer.Option(
        False,
        "--insecure",
    ),
) -> None:
    token_value = enrollment_token

    if token_stdin:
        token_value = (
            sys.stdin.read().strip()
        )

    if not token_value:
        token_value = typer.prompt(
            "Enrollment token",
            hide_input=True,
        ).strip()

    if not token_value:
        raise typer.BadParameter(
            "Enrollment token cannot "
            "be empty."
        )

    config = AgentConfig(
        backend_url=server.rstrip("/"),
        agent_id=None,
        name=name,
        cluster_name=cluster_name,
        environment=environment,
        namespaces=namespace,
        kube_context=kube_context,
        verify_tls=not insecure,
        collection_interval_seconds=(
            collection_interval
        ),
        heartbeat_interval_seconds=(
            heartbeat_interval
        ),
    )

    client = _client(
        config,
        None,
    )

    try:
        response = client.enroll(
            {
                "enrollment_token":
                    token_value,
                "name": name,
                "agent_type":
                    "kubernetes",
                "cluster_name":
                    cluster_name,
                "environment":
                    environment,
                "version":
                    __version__,
                "collection_interval_seconds":
                    collection_interval,
                "heartbeat_interval_seconds":
                    heartbeat_interval,
                "namespace_scope":
                    namespace,
                "capabilities": [
                    "kubernetes.discovery",
                ],
                "labels": {},
                "metadata": {
                    "kube_context":
                        kube_context,
                },
            }
        )

    except AgentClientError as exc:
        console.print(
            f"[red]Enrollment failed:"
            f"[/red] {exc}"
        )
        raise typer.Exit(1)

    finally:
        client.close()

    config.agent_id = str(
        response["agent_id"]
    )

    save_config(config)

    store_agent_token(
        str(
            response[
                "agent_token"
            ]
        )
    )

    console.print(
        "[green]Agent enrolled.[/green]"
    )

    console.print(
        f"Agent ID: {config.agent_id}"
    )

    console.print(
        f"Config: {config_path()}"
    )

    console.print(
        "Credentials: "
        f"{credentials_path()}"
    )


@app.command("doctor")
def doctor() -> None:
    config = load_config()

    result: dict[str, object] = {
        "agent_id":
            config.agent_id,
        "backend_url":
            config.backend_url,
        "cluster_name":
            config.cluster_name,
        "namespace_scope":
            config.namespaces,
        "config_file":
            str(config_path()),
        "credentials_file":
            str(
                credentials_path()
            ),
        "token_configured":
            bool(
                load_agent_token()
            ),
        "backend":
            "unknown",
        "kubernetes":
            "unknown",
    }

    client = _client(
        config,
        load_agent_token(),
    )

    try:
        health = client.health()

        result["backend"] = (
            health.get(
                "status",
                "available",
            )
        )

    except Exception as exc:
        result["backend"] = (
            "failed"
        )
        result["backend_error"] = (
            str(exc)
        )

    finally:
        client.close()

    try:
        collector = (
            KubernetesCollector(
                config
            )
        )

        probe = collector.doctor()

        result["kubernetes"] = (
            "available"
        )
        result.update(probe)

    except Exception as exc:
        result["kubernetes"] = (
            "failed"
        )
        result["kubernetes_error"] = (
            str(exc)
        )

    table = Table(
        title="Topo Agent Diagnostics"
    )

    table.add_column("Field")
    table.add_column("Value")

    for key, value in (
        result.items()
    ):
        table.add_row(
            str(key),
            json.dumps(value)
            if isinstance(
                value,
                (dict, list),
            )
            else str(value),
        )

    console.print(table)


@app.command("heartbeat")
def heartbeat() -> None:
    (
        config,
        client,
        collector,
        buffer,
    ) = _runtime()

    runner = AgentRunner(
        config=config,
        client=client,
        collector=collector,
        buffer=buffer,
    )

    try:
        response = runner.heartbeat()
        console.print_json(
            data=response
        )

    finally:
        client.close()


@app.command("collect")
def collect() -> None:
    (
        config,
        client,
        collector,
        buffer,
    ) = _runtime()

    runner = AgentRunner(
        config=config,
        client=client,
        collector=collector,
        buffer=buffer,
    )

    try:
        replayed = (
            runner.replay_buffer()
        )

        receipt = (
            runner.collect_once()
        )

        console.print_json(
            data={
                "replayed":
                    replayed,
                "receipt":
                    receipt,
                "buffered":
                    buffer.size(),
            }
        )

    finally:
        client.close()


@app.command("run")
def run(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
    ),
) -> None:
    _configure_logging(
        verbose
    )

    (
        config,
        client,
        collector,
        buffer,
    ) = _runtime()

    runner = AgentRunner(
        config=config,
        client=client,
        collector=collector,
        buffer=buffer,
    )

    try:
        runner.run()

    except KeyboardInterrupt:
        logging.getLogger(
            "topo-agent"
        ).info(
            "Topo Agent stopped."
        )

    finally:
        client.close()