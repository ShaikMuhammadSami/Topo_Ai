from __future__ import annotations

from dataclasses import dataclass

import typer
from rich.console import Console

from topo_cli.security import safe_error_text


console = Console(stderr=True)


class ExitCode:
    SUCCESS = 0
    CONFIGURATION = 2
    CONNECTION = 3
    AUTHENTICATION = 4
    NOT_FOUND = 5
    API_ERROR = 6
    VALIDATION = 7
    FILE_ERROR = 8
    AUTHORIZATION = 9


@dataclass
class TopoCliError(Exception):
    message: str
    exit_code: int

    def __post_init__(self) -> None:
        self.message = safe_error_text(self.message)

    def __str__(self) -> str:
        return self.message


class ConfigurationError(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.CONFIGURATION,
        )


class ConnectionFailure(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.CONNECTION,
        )


class AuthenticationFailure(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.AUTHENTICATION,
        )


class AuthorizationFailure(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.AUTHORIZATION,
        )


class ResourceNotFound(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.NOT_FOUND,
        )


class ApiFailure(TopoCliError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.status_code = status_code

        super().__init__(
            message=message,
            exit_code=ExitCode.API_ERROR,
        )


class InputValidationFailure(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.VALIDATION,
        )


class FileOperationFailure(TopoCliError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message=message,
            exit_code=ExitCode.FILE_ERROR,
        )


def abort(error: TopoCliError) -> None:
    console.print(
        f"[bold red]Error:[/bold red] "
        f"{safe_error_text(error.message)}"
    )

    raise typer.Exit(
        code=error.exit_code
    )
