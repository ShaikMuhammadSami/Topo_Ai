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
from topo_agent.config import (
    AgentConfig,
    buffer_directory,
    config_path,
    credentials_path,
    load_agent_token,
    preflight_agent_token_storage,
    load_config,
    save_config,
    store_agent_token,
)
from topo_agent.plugin_registry import (
    available_plugins,
    build_plugin_manager,
)
from topo_agent.runner import (
    AgentRunner,
)
from topo_agent.security import install_logging_redaction, safe_exception_message
from topo_agent.change_watch import (
    ChangeWatchRunner,
)
from topo_agent.change_watch_aws import (
    AwsCloudTrailChangePoller,
)
from topo_agent.change_watch_azure import (
    AzureActivityChangePoller,
)
from topo_agent.change_watch_gcp import (
    GcpAuditChangePoller,
)
from topo_agent.change_watch_kubernetes import (
    KubernetesChangePoller,
)


app = typer.Typer(
    name="topo-agent",
    help=(
        "Topo AI infrastructure "
        "discovery agent."
    ),
    no_args_is_help=True,
)

plugins_app = typer.Typer(
    help=(
        "Inspect and diagnose "
        "discovery plugins."
    ),
    no_args_is_help=True,
)

app.add_typer(
    plugins_app,
    name="plugins",
)

console = Console()


def _configure_logging(
    verbose: bool,
) -> None:
    install_logging_redaction()
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


def _runtime(
    *,
    selected_plugins:
        list[str] | None = None,
) -> tuple[
    AgentConfig,
    AgentApiClient,
    object,
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

    try:
        manager = (
            build_plugin_manager(
                config,
                selected_plugins=(
                    selected_plugins
                ),
            )
        )

    except Exception:
        client.close()
        raise

    buffer = SnapshotBuffer(
        buffer_directory(),
        max_items=(
            config.max_buffer_items
        ),
    )

    return (
        config,
        client,
        manager,
        buffer,
    )


def _build_change_watch_runner(
    config: AgentConfig,
    client: AgentApiClient,
) -> ChangeWatchRunner:
    logger = logging.getLogger(
        "topo-agent"
    )
    runner = ChangeWatchRunner(
        client=client,
        interval_seconds=(
            config
            .change_watch_interval_seconds
        ),
        defer_failure_signals=True,
    )

    if config.change_watch_kubernetes:
        try:
            runner.register(
                "kubernetes",
                KubernetesChangePoller(
                    cluster_name=(
                        config.cluster_name
                    ),
                    namespaces=config.namespaces,
                    kube_context=config.kube_context,
                    overlap_seconds=(
                        config
                        .change_watch_overlap_seconds
                    ),
                ),
            )

        except Exception as exc:
            logger.warning(
                "Kubernetes change watch is unavailable; "
                "periodic topology reconciliation remains "
                "active: %s",
                exc,
            )

    if config.change_watch_aws:
        try:
            runner.register(
                "aws",
                AwsCloudTrailChangePoller(
                    regions=config.aws_regions,
                    profile=config.aws_profile,
                    overlap_seconds=(
                        config
                        .change_watch_overlap_seconds
                    ),
                ),
            )

        except Exception as exc:
            logger.warning(
                "AWS change watch is unavailable; periodic "
                "topology reconciliation remains active: %s",
                exc,
            )

    if config.change_watch_azure:
        try:
            runner.register(
                "azure",
                AzureActivityChangePoller(
                    subscription_ids=(
                        config
                        .azure_subscription_ids
                    ),
                    overlap_seconds=(
                        config
                        .change_watch_overlap_seconds
                    ),
                ),
            )

        except Exception as exc:
            logger.warning(
                "Azure change watch is unavailable; "
                "periodic topology reconciliation remains "
                "active: %s",
                exc,
            )

    if config.change_watch_gcp:
        try:
            runner.register(
                "gcp",
                GcpAuditChangePoller(
                    project_ids=(
                        config.gcp_project_ids
                    ),
                    overlap_seconds=(
                        config
                        .change_watch_overlap_seconds
                    ),
                ),
            )

        except Exception as exc:
            logger.warning(
                "GCP change watch is unavailable; periodic "
                "topology reconciliation remains active: %s",
                exc,
            )

    return runner


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
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        help=(
            "Enabled plugin. Repeat for "
            "multiple plugins."
        ),
    ),
    kube_context: str | None = typer.Option(
        None,
        "--kube-context",
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
    try:
        preflight_agent_token_storage()
    except OSError:
        console.print(
            "[red]Enrollment cannot continue because secure local credential "
            "storage is unavailable.[/red]"
        )
        raise typer.Exit(1)

    token_value: str | None = None

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

    enabled_plugins = (
        plugin
        if plugin
        else ["kubernetes"]
    )

    unknown_plugins = sorted(
        set(enabled_plugins)
        - set(available_plugins())
    )

    if unknown_plugins:
        raise typer.BadParameter(
            "Unknown plugins: "
            + ", ".join(
                unknown_plugins
            )
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
        enabled_plugins=[
            value.lower()
            for value in enabled_plugins
        ],
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
                    "plugin",
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
                "capabilities": [],
                "labels": {},
                "metadata": {
                    "kube_context":
                        kube_context,
                    "enabled_plugins":
                        enabled_plugins,
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

    try:
        store_agent_token(str(response["agent_token"]))
    except OSError:
        console.print(
            "[red]Enrollment succeeded, but secure credential persistence failed. "
            "Revoke this agent from an authenticated workstation and enroll again.[/red]"
        )
        raise typer.Exit(1)

    console.print(
        "[green]Agent enrolled.[/green]"
    )

    console.print(
        f"Agent ID: {config.agent_id}"
    )

    console.print(
        "Plugins: "
        + ", ".join(
            config.enabled_plugins
        )
    )

    console.print(
        f"Config: {config_path()}"
    )


@plugins_app.command("list")
def list_plugins() -> None:
    config = load_config()

    table = Table(
        title="Topo Agent Plugins"
    )

    table.add_column("Plugin")
    table.add_column("Enabled")
    table.add_column(
        "Available"
    )

    available = (
        available_plugins()
    )

    for name in available:
        table.add_row(
            name,
            (
                "yes"
                if name
                in config.enabled_plugins
                else "no"
            ),
            "yes",
        )

    console.print(table)


@plugins_app.command("doctor")
def plugin_doctor(
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
    ),
) -> None:
    config = load_config()

    selected = (
        plugin
        if plugin
        else config.enabled_plugins
    )

    try:
        manager = (
            build_plugin_manager(
                config,
                selected_plugins=selected,
            )
        )

    except ValueError as exc:
        console.print(
            f"[red]{safe_exception_message(exc, 'Plugin configuration failed')}[/red]"
        )

        raise typer.Exit(1)

    try:
        results = (
            manager.diagnostics()
        )

    finally:
        manager.close()

    table = Table(
        title="Plugin Diagnostics"
    )

    table.add_column("Plugin")
    table.add_column("Status")
    table.add_column("Message")
    table.add_column("Details")

    for result in results:
        table.add_row(
            result.name,
            result.status,
            result.message or "-",
            json.dumps(
                result.details,
                default=str,
            ),
        )

    console.print(table)


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
        "enabled_plugins":
            config.enabled_plugins,
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
        "plugins":
            [],
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
            safe_exception_message(exc, "Backend health check failed")
        )

    finally:
        client.close()

    try:
        manager = (
            build_plugin_manager(
                config
            )
        )

        try:
            result["plugins"] = [
                item.to_dict()
                for item in
                manager.diagnostics()
            ]

        finally:
            manager.close()

    except Exception as exc:
        result["plugin_error"] = (
            safe_exception_message(exc, "Plugin diagnostics failed")
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
            json.dumps(
                value,
                default=str,
            )
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
        manager,
        buffer,
    ) = _runtime()

    runner = AgentRunner(
        config=config,
        client=client,
        plugin_manager=manager,
        buffer=buffer,
    )

    try:
        response = runner.heartbeat()

        console.print_json(
            data=response
        )

    finally:
        runner.close()


@app.command("collect")
def collect(
    plugin: list[str] = typer.Option(
        [],
        "--plugin",
        help=(
            "Collect only from the selected "
            "plugin. Repeat to select more."
        ),
    ),
) -> None:
    selected = (
        plugin
        if plugin
        else None
    )

    (
        config,
        client,
        manager,
        buffer,
    ) = _runtime(
        selected_plugins=selected
    )

    runner = AgentRunner(
        config=config,
        client=client,
        plugin_manager=manager,
        buffer=buffer,
    )

    try:
        replayed = (
            runner.replay_buffer()
        )

        receipt = (
            runner.collect_once(
                checkpoint_reason="manual"
            )
        )

        console.print_json(
            data={
                "plugins":
                    manager
                    .plugin_names(),
                "replayed":
                    replayed,
                "receipt":
                    receipt,
                "buffered":
                    buffer.size(),
                "plugin_status":
                    manager
                    .status_snapshot(),
            }
        )

    finally:
        runner.close()


@app.command("run")
def run(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
    ),
) -> None:
    _configure_logging(verbose)

    (
        config,
        client,
        manager,
        buffer,
    ) = _runtime()

    runner = AgentRunner(
        config=config,
        client=client,
        plugin_manager=manager,
        buffer=buffer,
        change_watch_runner=(
            _build_change_watch_runner(
                config,
                client,
            )
        ),
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
        runner.close()

@app.command("watch-changes")
def watch_changes(
    once: bool = typer.Option(
        False,
        "--once",
    ),
) -> None:
    config = load_config()

    token = load_agent_token()

    if not token:
        raise typer.BadParameter(
            "Topo Agent is not enrolled."
        )

    client = _client(
        config,
        token,
    )

    runner = ChangeWatchRunner(
        client=client,
        interval_seconds=(
            config
            .change_watch_interval_seconds
        ),
    )

    if (
        config
        .change_watch_kubernetes
    ):
        runner.register(
            "kubernetes",
            KubernetesChangePoller(
                cluster_name=(
                    config.cluster_name
                ),
                namespaces=config.namespaces,
                kube_context=config.kube_context,
                overlap_seconds=(
                    config
                    .change_watch_overlap_seconds
                ),
            ),
        )

    if config.change_watch_aws:
        runner.register(
            "aws",
            AwsCloudTrailChangePoller(
                regions=(
                    config.aws_regions
                ),
                profile=(
                    config.aws_profile
                ),
                overlap_seconds=(
                    config
                    .change_watch_overlap_seconds
                ),
            ),
        )

    if config.change_watch_azure:
        runner.register(
            "azure",
            AzureActivityChangePoller(
                subscription_ids=(
                    config
                    .azure_subscription_ids
                ),
                overlap_seconds=(
                    config
                    .change_watch_overlap_seconds
                ),
            ),
        )

    if config.change_watch_gcp:
        runner.register(
            "gcp",
            GcpAuditChangePoller(
                project_ids=(
                    config.gcp_project_ids
                ),
                overlap_seconds=(
                    config
                    .change_watch_overlap_seconds
                ),
            ),
        )

    try:
        if once:
            result = (
                runner.run_once()
            )

            console.print_json(
                data=result
            )

        else:
            runner.run_forever()

    finally:
        client.close()
