"""Structural backstop for explicit authority (not an ORM/global filter)."""

import ast
from pathlib import Path

from app.db.database import Base
from app.db.domain_ownership import REQUIRED_OWNERSHIP_TABLES, MACHINE_DEPENDENT_WRITERS

APP = Path(__file__).resolve().parents[1] / "app"
GLOBAL_REPOSITORIES = {
    "auth_session_repository",
    "auth_api_credential_repository",
    "tenant_repository",
    "tenant_scope",
    "principal_identity_repository",
    "authority_repository",
    "security_audit_repository",
}
MACHINE_FUNCTIONS = {
    "agent_repository.enroll_agent",
    "agent_repository.authenticate_agent",
    "change_source_repository.load_change_source_for_authentication",
}


def repository_inventory():
    result = []
    for path in sorted((APP / "repositories").glob("*.py")):
        if path.stem in GLOBAL_REPOSITORIES:
            continue
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = node.args.args + node.args.kwonlyargs
            if not any(a.arg == "session" for a in args):
                continue
            result.append((path.stem + "." + node.name, node))
    return result


def test_domain_repository_authority_is_required_not_optional():
    inventory = repository_inventory()
    for name, function in inventory:
        if name in MACHINE_FUNCTIONS:
            continue
        assert "tenant_id" in [a.arg for a in function.args.kwonlyargs], name
        position = [a.arg for a in function.args.kwonlyargs].index("tenant_id")
        assert function.args.kw_defaults[position] is None, name
    assert {name for name, _ in inventory} >= MACHINE_FUNCTIONS


def test_domain_get_cannot_use_unscoped_session_identity_map():
    owned = {
        mapper.class_.__name__
        for mapper in Base.registry.mappers
        if mapper.local_table.name
        in REQUIRED_OWNERSHIP_TABLES | MACHINE_DEPENDENT_WRITERS.keys()
    }
    for directory in ("repositories", "services"):
        for path in (APP / directory).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if ast.unparse(node.func) == "session.get":
                    assert ast.unparse(node.args[0]) not in owned, (
                        path.name,
                        node.lineno,
                    )


def test_unowned_authority_is_not_a_public_input_or_default():
    for path in APP.rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        for marker in ("UNOWNED_MACHINE", "DeferredMachineAuthority", "ph3e_unowned_machine"):
            assert marker not in source, path.name


def test_owned_sql_predicates_precede_query_execution():
    """Audit real SQL expression chains, not just the presence of an argument."""
    from app.db import models  # ensure all mapped classes are registered

    owned = {
        mapper.class_.__name__
        for mapper in models.Base.registry.mappers
        if mapper.local_table.name
        in REQUIRED_OWNERSHIP_TABLES | MACHINE_DEPENDENT_WRITERS.keys()
    }
    assert len(owned) == 38
    checked = 0
    for directory in ("repositories", "services"):
        for path in (APP / directory).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            parents = {
                child: parent for parent in ast.walk(tree)
                for child in ast.iter_child_nodes(parent)
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or ast.unparse(node.func) not in {
                    "select", "update", "delete",
                }:
                    continue
                selected = {
                    item.id for argument in node.args for item in ast.walk(argument)
                    if isinstance(item, ast.Name) and item.id in owned
                }
                if not selected:
                    continue
                chain = node
                while isinstance(parents.get(chain), ast.Attribute):
                    chain = parents[chain]
                    if isinstance(parents.get(chain), ast.Call):
                        chain = parents[chain]
                predicates = {
                    ast.unparse(item.args[0])
                    for item in ast.walk(chain)
                    if isinstance(item, ast.Call)
                    and ast.unparse(item.func) == "tenant_predicate"
                    and item.args
                }
                # Only three exact authentication derivation SELECTs precede
                # known tenant authority. Their equality predicate is audited
                # here; conditional enrollment UPDATE still requires tenancy.
                parent = node
                while parent in parents and not isinstance(parent, ast.FunctionDef):
                    parent = parents[parent]
                function = path.stem + "." + getattr(parent, "name", "")
                if function in MACHINE_FUNCTIONS and ast.unparse(node.func) == "select":
                    expected = {
                        "agent_repository.enroll_agent": "AgentEnrollmentTokenRecord.token_hash == digest",
                        "agent_repository.authenticate_agent": "TopoAgentRecord.token_hash == digest",
                        "change_source_repository.load_change_source_for_authentication": "ChangeSourceRecord.source_id == source_id",
                    }[function]
                    assert any(isinstance(item, ast.Compare) and ast.unparse(item) == expected
                               for item in ast.walk(chain)), (function, node.lineno)
                    continue
                assert selected <= predicates, (path.name, node.lineno, selected)
                checked += 1
    assert checked >= 35
