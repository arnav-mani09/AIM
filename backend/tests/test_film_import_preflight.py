import builtins
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import film_import_preflight as preflight


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.environment = {
            "DATABASE_URL": "postgresql+psycopg://private-user:private-password@private-db/film",
            "SECRET_KEY": "private-signing-key",
            "R2_ACCOUNT_ID": "private-account",
            "R2_ACCESS_KEY_ID": "private-access",
            "R2_SECRET_ACCESS_KEY": "private-storage-secret",
        }
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()
        patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")).start()
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path.name.startswith(".env") or path.name == ".modal.toml":
                raise AssertionError("Private configuration must not be read")
            return original_open(path, *args, **kwargs)

        patch.object(Path, "open", guarded_open).start()

    def report(self, **kwargs):
        return preflight.build_report(self.environment, **kwargs)

    def check(self, report, name):
        return next(check for check in report["checks"] if check["check"] == name)

    def fixture_root(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for relative in (
            "backend/app/core/config.py", "worker/film_worker.py",
            "backend/app/services/film_import_download.py",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(preflight.ROOT / relative, destination)
        shutil.copytree(preflight.ROOT / "backend/alembic/versions", root / "backend/alembic/versions")
        return root

    def test_disabled_defaults_are_only_direct_upload_prerequisites(self):
        with patch.object(preflight, "database_heads", side_effect=AssertionError("Database forbidden")):
            report = self.report()
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["scope"], "direct_upload_only")
        self.assertFalse(report["release_ready"])
        self.assertFalse(report["import_enabled"])
        self.assertEqual(self.check(report, "local_migrations")["status"], "verified")
        self.assertEqual(self.check(report, "database_migration_head")["status"], "not_checked")

    def test_enabled_with_hosts_is_configured_not_live_verified(self):
        self.environment.update(FILM_IMPORT_ENABLED="true", FILM_IMPORT_ALLOWED_HOSTS=" CDN.Example.com , media.example.com ")
        report = self.report()
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["scope"], "film_import")
        self.assertEqual(self.check(report, "FILM_IMPORT_ALLOWED_HOSTS")["status"], "configured")
        for name in ("modal_deployment", "r2_runtime", "production_schema", "provider_compatibility"):
            self.assertEqual(self.check(report, name)["status"], "not_checked")
        self.assertFalse(report["release_ready"])

    def test_enabled_requires_nonempty_hosts(self):
        self.environment["FILM_IMPORT_ENABLED"] = "true"
        self.assertEqual(self.report()["exit_code"], 1)

    def test_bad_hosts_are_blockers_even_if_import_disabled(self):
        for hosts in ("*.example.com", "https://cdn.example.com/private?token=secret", "127.0.0.1",
                      "[::1]", "cdn.example.com:443", "user@cdn.example.com", "cdn.example.com,",
                      "cdn.example.com,,media.example.com", "cdn.example.com/path", "localhost",
                      "-cdn.example.com", "cdn_.example.com", "cdn.example.com.", "café.example.com",
                      "cdn.\nexample.com", "", "a" * 64 + ".com"):
            with self.subTest(hosts=hosts):
                self.environment.update(FILM_IMPORT_ENABLED="true", FILM_IMPORT_ALLOWED_HOSTS=hosts)
                report = self.report()
                self.assertEqual(self.check(report, "FILM_IMPORT_ALLOWED_HOSTS")["status"], "invalid")
                self.assertEqual(report["exit_code"], 1)
                if hosts:
                    self.environment["FILM_IMPORT_ENABLED"] = "false"
                    self.assertEqual(self.report()["exit_code"], 1)

    def test_boolean_spellings_and_invalid_values(self):
        self.environment["FILM_IMPORT_ALLOWED_HOSTS"] = "cdn.example.com"
        for value in ("true", "TRUE", "1", "yes", "on", "t", "y"):
            self.environment["FILM_IMPORT_ENABLED"] = value
            self.assertTrue(self.report()["import_enabled"])
        for value in ("false", "FALSE", "0", "no", "off", "f", "n"):
            self.environment["FILM_IMPORT_ENABLED"] = value
            self.assertFalse(self.report()["import_enabled"])
        for name in ("FILM_IMPORT_ENABLED", "DETECTION_ENABLED"):
            self.environment[name] = "not-a-boolean"
            self.assertEqual(self.report()["exit_code"], 1)

    def test_missing_required_values_block_both_scopes(self):
        for enabled in ("true", "false"):
            for name in (*self.environment, "R2_BUCKET", "MODAL_FILM_APP"):
                with self.subTest(enabled=enabled, name=name):
                    environment = dict(self.environment, FILM_IMPORT_ENABLED=enabled,
                                       FILM_IMPORT_ALLOWED_HOSTS="cdn.example.com")
                    environment[name] = " "
                    report = preflight.build_report(environment)
                    self.assertEqual(report["exit_code"], 1)
                    self.assertEqual(self.check(report, name)["status"], "invalid")

    def test_modal_credentials_are_presence_only_and_render_requires_pair(self):
        self.assertEqual(self.check(self.report(), "modal_credentials")["status"], "not_checked")
        self.environment["RENDER"] = "true"
        self.assertEqual(self.report()["exit_code"], 1)
        self.environment["MODAL_TOKEN_ID"] = "private-modal-id"
        self.assertEqual(self.report()["exit_code"], 1)
        self.environment["MODAL_TOKEN_SECRET"] = "private-modal-secret"
        self.assertEqual(self.check(self.report(), "modal_credentials")["status"], "configured")

    def test_environment_is_explicit_and_no_dotenv_loaded(self):
        with patch.dict(os.environ, {"FILM_IMPORT_ENABLED": "true", "FILM_IMPORT_ALLOWED_HOSTS": "bad://private"}):
            self.assertEqual(self.report()["exit_code"], 0)

    def test_offline_mode_does_not_import_application_or_service_clients(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in {"app", "modal", "boto3", "psycopg", "sqlalchemy", "alembic"}:
                raise AssertionError("Offline checks must not load runtime dependencies")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            self.assertEqual(self.report()["exit_code"], 0)

    def test_local_head_and_missing_import_migration(self):
        root = self.fixture_root()
        self.assertEqual(preflight.migration_heads(root), ["0016"])
        (root / "backend/alembic/versions/0016_film_import.py").unlink()
        report = self.report(root=root)
        self.assertEqual(self.check(report, "local_migrations")["status"], "invalid")
        self.assertEqual(report["exit_code"], 1)

    def test_broken_migration_graph_is_not_verified(self):
        for contents in (
            'revision = "extra"\ndown_revision = "missing"\n',
            'revision = "extra"\ndown_revision = "extra"\n',
            'revision = "extra"\ndown_revision = "0015"\n',
            'revision = "0016"\ndown_revision = "0015"\n',
            'not valid python !',
        ):
            with self.subTest(contents=contents):
                root = self.fixture_root()
                (root / "backend/alembic/versions/extra.py").write_text(contents)
                self.assertEqual(self.report(root=root)["exit_code"], 1)

    def test_missing_settings_cannot_silently_certify_defaults(self):
        root = self.fixture_root()
        (root / "backend/app/core/config.py").unlink()
        self.assertEqual(self.report(root=root)["exit_code"], 1)

    def test_worker_functions_app_and_detection_contract(self):
        self.environment.update(FILM_IMPORT_ENABLED="true", FILM_IMPORT_ALLOWED_HOSTS="cdn.example.com", DETECTION_ENABLED="true")
        self.assertEqual(self.report()["exit_code"], 0)
        root = self.fixture_root()
        path = root / "worker/film_worker.py"
        path.write_text(path.read_text().replace("def detect_players(", "def missing_detection("))
        self.assertEqual(self.check(self.report(root=root), "local_worker")["status"], "invalid")
        self.environment["MODAL_FILM_APP"] = "private-other-app"
        self.assertEqual(self.report()["exit_code"], 1)

    def test_missing_worker_import_contract_is_blocking(self):
        root = self.fixture_root()
        path = root / "worker/film_worker.py"
        path.write_text(path.read_text().replace("FILM_IMPORT_SOURCE_URL", "REMOVED_SOURCE"))
        self.environment.update(FILM_IMPORT_ENABLED="true", FILM_IMPORT_ALLOWED_HOSTS="cdn.example.com")
        self.assertEqual(self.report(root=root)["exit_code"], 1)

    def test_explicit_database_flag_only_and_head_comparison(self):
        for actual, expected in ((["0016"], 0), (["0015"], 1), ([], 1), (["0016", "extra"], 1)):
            with self.subTest(actual=actual), patch.object(preflight, "database_heads", return_value=actual) as query:
                report = self.report(check_database=True)
                self.assertEqual(report["exit_code"], expected)
                query.assert_called_once_with(self.environment["DATABASE_URL"])
                self.assertFalse(report["release_ready"])
                self.assertEqual(self.check(report, "production_schema")["status"], "not_checked")

    def test_failed_database_check_is_unchecked_and_redacted(self):
        with patch.object(preflight, "database_heads", side_effect=RuntimeError(self.environment["DATABASE_URL"])):
            report = self.report(check_database=True)
        self.assertEqual(report["exit_code"], 3)
        self.assertEqual(self.check(report, "database_migration_head")["status"], "not_checked")
        self.assertNotIn("private-db", json.dumps(report))

    def test_invalid_local_migrations_prevent_database_connection(self):
        root = self.fixture_root()
        (root / "backend/alembic/versions/0016_film_import.py").unlink()
        with patch.object(preflight, "database_heads") as query:
            self.assertEqual(self.report(root=root, check_database=True)["exit_code"], 1)
            query.assert_not_called()

    def test_database_rejects_unsupported_or_unsafe_urls_without_connecting(self):
        with patch.dict(sys.modules, {"psycopg": SimpleNamespace(connect=Mock())}):
            for url in ("sqlite:///private.db", "postgresql:///film", "postgresql://db/film?options=private",
                        "postgresql://db/film#fragment", "postgresql://db/", "mysql://db/film"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    preflight.database_heads(url)
            sys.modules["psycopg"].connect.assert_not_called()

    def test_database_uses_only_select_readonly_timeouts_rollback_and_close(self):
        cursor = Mock()
        cursor.fetchone.return_value = ("on",)
        cursor.fetchall.return_value = [("0016",)]
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        driver = SimpleNamespace(connect=Mock(return_value=connection))
        with patch.dict(sys.modules, {"psycopg": driver}):
            self.assertEqual(preflight.database_heads(self.environment["DATABASE_URL"]), ["0016"])
        options = driver.connect.call_args.kwargs
        self.assertFalse(options["autocommit"])
        self.assertEqual(options["connect_timeout"], 5)
        self.assertIn("default_transaction_read_only=on", options["options"])
        self.assertIn("statement_timeout=5000", options["options"])
        self.assertEqual([call.args[0] for call in cursor.execute.call_args_list], [
            "SELECT current_setting('transaction_read_only')", "SELECT version_num FROM alembic_version",
        ])
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()
        connection.commit.assert_not_called()

    def test_database_refuses_non_readonly_transaction_and_closes(self):
        cursor = Mock()
        cursor.fetchone.return_value = ("off",)
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(sys.modules, {"psycopg": SimpleNamespace(connect=Mock(return_value=connection))}):
            with self.assertRaises(ValueError):
                preflight.database_heads(self.environment["DATABASE_URL"])
        self.assertEqual(cursor.execute.call_count, 1)
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()

    def test_database_query_failure_still_rolls_back_and_closes(self):
        cursor = Mock()
        cursor.fetchone.return_value = ("on",)
        cursor.fetchall.side_effect = RuntimeError("private-database-details")
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.dict(sys.modules, {"psycopg": SimpleNamespace(connect=Mock(return_value=connection))}):
            report = self.report(check_database=True)
        self.assertEqual(report["exit_code"], 3)
        self.assertNotIn("private-database-details", json.dumps(report))
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()

    def test_missing_database_driver_remains_unchecked(self):
        with patch.dict(sys.modules, {"psycopg": None}):
            self.assertEqual(self.report(check_database=True)["exit_code"], 3)

    def test_json_and_human_output_never_echo_environment_values(self):
        self.environment.update(FILM_IMPORT_ENABLED="true", FILM_IMPORT_ALLOWED_HOSTS="https://private-source.example/film?token=private-token",
                                MODAL_TOKEN_ID="private-modal-id", MODAL_TOKEN_SECRET="private-modal-secret")
        for arguments in ([], ["--json"]):
            with self.subTest(arguments=arguments), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(preflight.main(arguments, environment=self.environment), 1)
            rendered = output.getvalue()
            for secret in self.environment.values():
                if secret != "true":
                    self.assertNotIn(secret, rendered)
            self.assertNotIn("private-", rendered)
            if arguments:
                self.assertFalse(json.loads(rendered)["release_ready"])
            else:
                self.assertIn("NOT CERTIFIED", rendered)

    def test_argument_errors_do_not_echo_private_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit) as raised:
            preflight.main(["--source-url=https://private.example/?secret=private-token"], environment={})
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn("private", output.getvalue())

    def test_database_flag_cannot_be_abbreviated(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            preflight.main(["--check-d"], environment=self.environment)
        self.assertEqual(raised.exception.code, 2)

    def test_executable_cli_from_unrelated_working_directory(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(preflight.ROOT / "backend/tools/film_import_preflight.py"), "--json"],
                cwd=directory, env=self.environment, capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"], "direct_upload_only")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
