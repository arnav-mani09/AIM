#!/usr/bin/env python3
"""Offline, value-free film release checks; never import application settings."""

import argparse
import ast
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
BOOLEAN_TRUE = {"1", "true", "t", "yes", "y", "on"}
BOOLEAN_FALSE = {"0", "false", "f", "no", "n", "off"}


def read_tree(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def literals(tree):
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        else:
            continue
        if isinstance(target, ast.Name):
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def boolean(value):
    normalized = str(value).lower()
    if normalized in BOOLEAN_TRUE:
        return True
    if normalized in BOOLEAN_FALSE:
        return False
    raise ValueError("Invalid boolean")


def valid_hosts(value):
    if not value.strip():
        return False
    for entry in value.split(","):
        host = entry.strip().lower()
        labels = host.split(".")
        if len(host) > 253 or len(labels) < 2:
            return False
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
            return False
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return False
        if labels[-1].isdigit():
            return False
    return True


def migration_heads(root):
    revisions = {}
    import_columns = set()
    for path in sorted((root / "backend/alembic/versions").glob("*.py")):
        tree = read_tree(path)
        values = literals(tree)
        revision = values.get("revision")
        if not isinstance(revision, str) or not revision or revision in revisions:
            raise ValueError("Invalid revision")
        parent = values.get("down_revision")
        parents = () if parent is None else (parent,) if isinstance(parent, str) else tuple(parent)
        if not all(isinstance(item, str) for item in parents):
            raise ValueError("Invalid parent")
        revisions[revision] = parents
        if revision == "0016":
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "add_column" or len(node.args) < 2:
                    continue
                table, column = node.args[:2]
                if (isinstance(table, ast.Constant) and table.value == "game_upload"
                        and isinstance(column, ast.Call) and column.args
                        and isinstance(column.args[0], ast.Constant)):
                    import_columns.add(column.args[0].value)
    if not {"import_job_id", "import_started_at"} <= import_columns:
        raise ValueError("Missing import migration")
    visited = set()

    def visit(revision, active):
        if revision not in revisions or revision in active:
            raise ValueError("Broken migration graph")
        if revision in visited:
            return
        for parent in revisions[revision]:
            visit(parent, active | {revision})
        visited.add(revision)

    for revision in revisions:
        visit(revision, set())
    parents = {parent for ancestors in revisions.values() for parent in ancestors}
    heads = sorted(set(revisions) - parents)
    if len(heads) != 1:
        raise ValueError("Resolve migration branches")
    return heads


def worker_contract(root, enabled, detection, app_name):
    tree = read_tree(root / "worker/film_worker.py")
    required = {"make_proxy"}
    if enabled:
        required.add("import_film")
    if detection:
        required.update({"detect_players", "make_events"})
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in required:
        function = functions.get(name)
        if function is None or not any(
            isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app"
            and decorator.func.attr == "function" for decorator in function.decorator_list
        ):
            raise ValueError("Missing local worker function")
    apps = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == "App"
            and node.args and isinstance(node.args[0], ast.Constant)]
    if len(apps) != 1 or apps[0].args[0].value != app_name:
        raise ValueError("Worker app differs from configuration")
    if enabled:
        function_text = ast.dump(functions["import_film"])
        for name in ("FILM_IMPORT_SOURCE_URL", "FILM_IMPORT_ALLOWED_HOSTS", "R2_BUCKET", "aim-r2", "import_to_r2"):
            if name not in function_text:
                raise ValueError("Import contract missing")
        if not (root / "backend/app/services/film_import_download.py").is_file():
            raise ValueError("Downloader missing")


def database_heads(database_url):
    """The only network entrypoint. Use server-enforced read-only transactions."""
    parsed = urlsplit(database_url)
    if (parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgres"}
            or not parsed.hostname or not parsed.path.strip("/") or parsed.query or parsed.fragment):
        raise ValueError("Only explicit PostgreSQL URLs without query options are supported")
    import psycopg

    connection = psycopg.connect(
        "postgresql:" + database_url.split(":", 1)[1],
        autocommit=False,
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('transaction_read_only')")
            if cursor.fetchone() != ("on",):
                raise ValueError("Read-only transaction required")
            cursor.execute("SELECT version_num FROM alembic_version")
            return sorted(row[0] for row in cursor.fetchall())
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def build_report(environment, root=ROOT, check_database=False):
    checks = []

    def add(name, status, message, blocking=False):
        checks.append({"check": name, "status": status, "blocking": blocking, "message": message})

    defaults = {}
    try:
        tree = read_tree(root / "backend/app/core/config.py")
        settings = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings")
        defaults = literals(settings)
        for name in ("film_import_enabled", "film_import_allowed_hosts", "modal_film_app", "r2_bucket", "detection_enabled"):
            if name not in defaults:
                raise ValueError("Settings contract missing")
        add("settings_contract", "verified", "Local Settings defaults read statically; no application or .env loaded.")
    except (OSError, SyntaxError, ValueError, TypeError, StopIteration):
        add("settings_contract", "invalid", "Restore the local Settings contract before using this tool.", True)

    def value(name):
        return environment.get(name, defaults.get(name.lower(), ""))

    enabled = False
    detection = False
    for name in ("FILM_IMPORT_ENABLED", "DETECTION_ENABLED"):
        try:
            parsed = boolean(value(name))
            if name == "FILM_IMPORT_ENABLED":
                enabled = parsed
            else:
                detection = parsed
            add(name, "configured", "Enabled in supplied environment/defaults." if parsed else "Disabled in supplied environment/defaults.")
        except ValueError:
            add(name, "invalid", "Set a recognized boolean such as true or false.", True)

    for name in ("DATABASE_URL", "SECRET_KEY", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "MODAL_FILM_APP"):
        present = bool(str(value(name)).strip())
        add(name, "configured" if present else "invalid",
            "Present; value and credentials not validated." if present else "Set this variable in the target backend environment.", not present)

    hosts = str(value("FILM_IMPORT_ALLOWED_HOSTS"))
    if not hosts.strip() and not enabled:
        add("FILM_IMPORT_ALLOWED_HOSTS", "not_checked", "Empty is allowed only while import is disabled.")
    elif valid_hosts(hosts):
        add("FILM_IMPORT_ALLOWED_HOSTS", "configured", "Exact DNS hostname syntax accepted; DNS, ownership, redirects and authorization not checked.")
    else:
        add("FILM_IMPORT_ALLOWED_HOSTS", "invalid", "Use comma-separated exact ASCII DNS hostnames; no URLs, ports, IPs, wildcards or empty entries.", True)

    token_id = bool(str(environment.get("MODAL_TOKEN_ID", "")).strip())
    token_secret = bool(str(environment.get("MODAL_TOKEN_SECRET", "")).strip())
    if token_id and token_secret:
        add("modal_credentials", "configured", "Token pair present; account access not validated.")
    elif token_id or token_secret or environment.get("RENDER"):
        add("modal_credentials", "invalid", "Set both MODAL_TOKEN_ID and MODAL_TOKEN_SECRET for the backend runtime.", True)
    else:
        add("modal_credentials", "not_checked", "No token pair supplied; local Modal profile is not read. Provision runtime credentials separately.")

    heads = []
    try:
        heads = migration_heads(root)
        add("local_migrations", "verified", "Local migration graph has one head and import columns in revision 0016; nothing applied.")
    except (OSError, SyntaxError, ValueError, TypeError, RecursionError):
        add("local_migrations", "invalid", "Restore a complete single-head migration chain including import columns in revision 0016.", True)
    try:
        worker_contract(root, enabled, detection, value("MODAL_FILM_APP"))
        add("local_worker", "verified", "Required decorated worker entrypoints and app name match local configuration; static inspection only.")
    except (OSError, SyntaxError, ValueError, TypeError):
        add("local_worker", "invalid", "Restore required worker entrypoints/import contract and align MODAL_FILM_APP with the local worker app.", True)

    database_verified = False
    if check_database and heads and str(value("DATABASE_URL")).strip():
        try:
            actual = database_heads(str(value("DATABASE_URL")))
            if actual == heads:
                database_verified = True
                add("database_migration_head", "verified", "Configured database revision equals the local head; schema contents and production identity not verified.")
            else:
                add("database_migration_head", "invalid", "Configured database revision differs from local head; use the normal release migration procedure, then recheck.", True)
        except Exception:
            add("database_migration_head", "not_checked", "Read-only head check unavailable: verify driver, connectivity, SELECT permission and PostgreSQL URL without query options. Details suppressed.")
    else:
        add("database_migration_head", "not_checked", "No database connection made. Supply --check-database with valid configuration/local migrations to opt in.")

    for name, message in (
        ("modal_deployment", "Verify deployed functions, app/account/environment, aim-r2 secret, ffmpeg/ffprobe, 5 GiB temporary disk and timeouts outside this tool."),
        ("r2_runtime", "Verify bucket credentials, CORS/playback access and lifecycle abort of incomplete multipart uploads; also reconcile orphaned completed objects."),
        ("production_schema", "Migration head alone does not prove columns, schema/search_path, permissions or production database identity."),
        ("provider_compatibility", "No source fetched. Hudl watch/share/login pages, HLS/DASH, cookies and DRM are unsupported; use an authorized direct MP4/MOV or direct upload."),
    ):
        add(name, "not_checked", message)

    blocked = any(check["blocking"] for check in checks)
    exit_code = 1 if blocked else 3 if check_database and not database_verified else 0
    return {
        "report_version": 1,
        "scope": "film_import" if enabled else "direct_upload_only",
        "local_prerequisites_passed": not blocked,
        "release_ready": False,
        "import_enabled": enabled,
        "database_check_requested": check_database,
        "exit_code": exit_code,
        "summary": "Local prerequisite blockers found." if blocked else "Selected-scope local prerequisites pass only; live release readiness remains unverified.",
        "checks": checks,
    }


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid arguments. Use --help; do not supply secrets or source URLs as arguments.\n")


def main(argv=None, environment=None):
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--json", action="store_true", help="Emit structured, value-free JSON.")
    parser.add_argument("--check-database", action="store_true", help="Opt in to a read-only PostgreSQL migration-head connection (no migrations).")
    arguments = parser.parse_args(argv)
    report = build_report(dict(os.environ) if environment is None else environment,
                          check_database=arguments.check_database)
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("Film release preflight — scope: " + report["scope"])
        print(report["summary"])
        print("Release ready: NOT CERTIFIED (configured is not verified).")
        for check in report["checks"]:
            print("[{status}] {check}: {message}".format(**check))
        print("Exit code: " + str(report["exit_code"]))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
