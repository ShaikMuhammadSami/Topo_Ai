from __future__ import annotations

import json
import logging

import typer
from topo_agent.security import install_logging_redaction, safe_exception_message
from rich.console import Console
from rich.table import Table

from topo_agent import __version__
from topo_agent.sensor import (
    SensorConfig,
    TopoRuntimeSensor,
)


app = typer.Typer(
    name="topo-sensor",
    help=(
        "Topo AI Tetragon event "
        "aggregation sensor."
    ),
    no_args_is_help=True,
)

console = Console()


def _sensor(
) -> TopoRuntimeSensor:
    try:
        config = (
            SensorConfig
            .from_environment()
        )

        return TopoRuntimeSensor(
            config
        )

    except ValueError as exc:
        raise typer.BadParameter(
            safe_exception_message(exc, "Sensor startup failed")
        ) from exc


@app.command("version")
def version() -> None:
    typer.echo(
        f"topo-sensor {__version__}"
    )


@app.command("doctor")
def doctor() -> None:
    sensor = _sensor()

    try:
        result = sensor.doctor()

    finally:
        sensor.close()

    table = Table(
        title="Topo Sensor Diagnostics"
    )

    table.add_column("Field")
    table.add_column("Value")

    for key, value in result.items():
        table.add_row(
            str(key),
            json.dumps(
                value,
                default=str,
            )
            if isinstance(
                value,
                (list, dict),
            )
            else str(value),
        )

    console.print(table)


@app.command("once")
def once() -> None:
    sensor = _sensor()

    try:
        result = sensor.run_once()

    finally:
        sensor.close()

    console.print_json(
        data=result
    )


@app.command("run")
def run(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
    ),
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

    sensor = _sensor()

    try:
        sensor.run()

    except KeyboardInterrupt:
        logging.getLogger(
            "topo-sensor"
        ).info(
            "Topo sensor stopped."
        )

    finally:
        sensor.close()
