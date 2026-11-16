import importlib.util
import io
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "feature_request_deploy", Path(__file__).resolve().parents[1] / ".deploy/fabfile.py"
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
restore_static_release = deploy.restore_static_release


class StaticReleaseTest(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.connection = Mock()
        self.previous = "a" * 40
        self.target = "b" * 40
        self.paths = "projects/static/projects/app.js\n.deploy/fabfile.py\ntests/test_deploy.py\n"
        self.commands = []
        for name, value in (
            ("PROJECT_ROOT", self.root),
            ("git_command", Mock()),
            ("public_smoke", Mock()),
            ("debug", Mock()),
            ("run_as_app_user", Mock(side_effect=self.run_command)),
        ):
            patcher = patch.object(deploy, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_command(self, connection, command, **kwargs):
        self.commands.append(command)
        output = self.previous if command == "git rev-parse HEAD" else ""
        if command == "git rev-parse origin/main":
            output = self.target
        elif command.startswith("git diff --name-only"):
            output = self.paths
        return SimpleNamespace(stdout=output)

    def test_static_preflight_records_verified_previous_revision(self):
        self.assertEqual(
            deploy.prepare_static_release(self.connection, None), (self.previous, self.target)
        )
        self.assertTrue(any("manage.py migrate --check" in command for command in self.commands))
        self.assertTrue(any("makemigrations --check --dry-run" in command for command in self.commands))
        self.assertIn(".deploy-previous-revision", self.commands[-1])
        self.assertIn(self.previous, self.commands[-1])
        deploy.public_smoke.assert_called_once_with(self.connection)

    def test_non_static_changes_are_rejected_before_activation(self):
        for path in ("projects/models.py", "projects/migrations/0010_change.py", "uv.lock", ".env", "packages/library.py"):
            with self.subTest(path=path):
                self.commands.clear()
                self.paths = path
                with self.assertRaisesRegex(RuntimeError, "non-static changes"):
                    deploy.prepare_static_release(self.connection, None)
                self.assertFalse(any(".deploy-previous-revision" in command for command in self.commands))
        deploy.public_smoke.assert_not_called()

    def test_environment_changes_are_rejected_without_exposing_values(self):
        (self.root / ".env-prod").write_bytes(b"local-test-value")
        self.connection.sftp.return_value.open.return_value = io.BytesIO(b"remote-test-value")
        with self.assertRaisesRegex(RuntimeError, "cannot change the server environment"):
            deploy.prepare_static_release(self.connection, None)
        deploy.public_smoke.assert_not_called()

    def test_pending_migrations_prevent_activation(self):
        def pending(connection, command, **kwargs):
            if "manage.py migrate --check" in command:
                raise RuntimeError("pending migrations")
            return self.run_command(connection, command, **kwargs)

        deploy.run_as_app_user.side_effect = pending
        with self.assertRaisesRegex(RuntimeError, "pending migrations"):
            deploy.prepare_static_release(self.connection, None)
        self.assertFalse(any(".deploy-previous-revision" in command for command in self.commands))
        deploy.public_smoke.assert_not_called()

    def test_changed_remote_target_is_rejected_before_checkout(self):
        self.connection.run.return_value.ok = True
        with self.assertRaisesRegex(RuntimeError, "changed after release preflight"):
            deploy.ensure_checkout(
                self.connection, source_url="https://example.test/repo.git", token=None,
                expected_revision="c" * 40,
            )
        self.assertFalse(any(command.startswith("git checkout") or command.startswith("git reset") for command in self.commands))


class StaticDeployRecoveryTest(TestCase):
    def setUp(self):
        self.connection = Mock()
        self.previous = "a" * 40
        self.target = "b" * 40
        patches = {
            "Connection": Mock(return_value=self.connection),
            "require_env": Mock(return_value="test"),
            "repo_url": Mock(return_value="https://example.test/repo.git"),
            "get_github_token": Mock(return_value=None),
            "pause_stageops_cron": Mock(return_value=nullcontext()),
            "prepare_static_release": Mock(return_value=(self.previous, self.target)),
            "ensure_checkout": Mock(),
            "upload_environment": Mock(),
            "install_dependencies": Mock(),
            "run_django_release": Mock(),
            "run_as_app_user": Mock(),
            "verify_revision": Mock(),
            "restart_mcp_runtime": Mock(),
            "restart_web": Mock(),
            "public_smoke": Mock(),
            "restore_static_release": Mock(),
            "debug": Mock(),
        }
        for name, value in patches.items():
            patcher = patch.object(deploy, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_static_deploy_skips_environment_dependencies_and_migration_writes(self):
        deploy.deploy.body(None, static_only=True)
        deploy.upload_environment.assert_not_called()
        deploy.install_dependencies.assert_not_called()
        deploy.run_django_release.assert_not_called()
        deploy.restore_static_release.assert_not_called()
        self.assertEqual(deploy.ensure_checkout.call_args.kwargs["expected_revision"], self.target)
        self.assertEqual(deploy.verify_revision.call_count, 2)

    def test_activation_failure_restores_previous_release_while_holding_lock(self):
        held = []

        @contextmanager
        def lock(connection):
            held.append(True)
            try:
                yield
            finally:
                held.pop()

        def restore(connection, previous):
            self.assertTrue(held)
            self.assertEqual(previous, self.previous)

        deploy.pause_stageops_cron.side_effect = lock
        deploy.restore_static_release.side_effect = restore
        deploy.restart_web.side_effect = RuntimeError("activation failed")
        with self.assertRaisesRegex(RuntimeError, "activation failed"):
            deploy.deploy.body(None, static_only=True)
        deploy.restore_static_release.assert_called_once_with(self.connection, self.previous)
        self.assertFalse(held)

    def test_failed_preflight_does_not_update_or_restore_checkout(self):
        deploy.prepare_static_release.side_effect = RuntimeError("unsafe candidate")
        with self.assertRaisesRegex(RuntimeError, "unsafe candidate"):
            deploy.deploy.body(None, static_only=True)
        deploy.ensure_checkout.assert_not_called()
        deploy.restore_static_release.assert_not_called()

    def test_recovery_restores_assets_and_verifies_schema_before_restart(self):
        steps = []
        deploy.run_as_app_user.side_effect = lambda connection, command, **kwargs: steps.append(command)
        deploy.verify_revision.side_effect = lambda connection, revision: steps.append(("verify", revision))
        deploy.restart_mcp_runtime.side_effect = lambda connection: steps.append("mcp")
        deploy.restart_web.side_effect = lambda connection: steps.append("web")
        deploy.public_smoke.side_effect = lambda connection: steps.append("health")
        restore_static_release(self.connection, self.previous)
        self.assertEqual(steps[0], f"git reset --hard {self.previous}")
        self.assertTrue(any("collectstatic --noinput" in step for step in steps if isinstance(step, str)))
        self.assertEqual(steps[-4:], [("verify", self.previous), "mcp", "web", "health"])
        self.assertFalse(any("migrate --noinput" in step for step in steps if isinstance(step, str)))


class FullDeploySafetyTest(TestCase):
    def setUp(self):
        self.connection = Mock()
        self.cron_paused = False
        self.steps = []
        self.connection.sudo.side_effect = self.sudo
        patches = {
            "Connection": Mock(return_value=self.connection),
            "require_env": Mock(return_value="test"),
            "repo_url": Mock(return_value="https://example.test/repo.git"),
            "get_github_token": Mock(return_value=None),
            "pause_stageops_cron": Mock(return_value=nullcontext()),
            "prepare_release": Mock(return_value=("a" * 40, "b" * 40)),
            "debug": Mock(),
        }
        for name in (
            "ensure_checkout", "upload_environment", "install_dependencies",
            "run_django_release", "verify_revision", "restart_mcp_runtime",
            "restart_web", "public_smoke",
        ):
            patches[name] = Mock(side_effect=lambda *args, step=name, **kwargs: self.steps.append(step))
        for name, value in patches.items():
            patcher = patch.object(deploy, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def sudo(self, command, **kwargs):
        if command.startswith("test -e"):
            return SimpleNamespace(ok=self.cron_paused)
        if command.startswith("test -f"):
            return SimpleNamespace(ok=True)
        if command == f"mv -- {deploy.STAGEOPS_CRONTAB} {deploy.PAUSED_CRONTAB}":
            self.cron_paused = True
            self.steps.append("pause_cron")
        elif command == f"mv -- {deploy.PAUSED_CRONTAB} {deploy.STAGEOPS_CRONTAB}":
            self.cron_paused = False
            self.steps.append("resume_cron")
        elif command.startswith("systemctl stop"):
            for unit in (f"app@{deploy.PROJECT_NAME}.socket", f"app@{deploy.PROJECT_NAME}.service", deploy.MCP_SERVICE):
                self.assertIn(unit, command)
            self.steps.append("stop_runtime")
        return SimpleNamespace(ok=True)

    def test_code_and_schema_change_only_while_consumers_are_stopped(self):
        deploy.deploy.body(None)
        self.assertLess(self.steps.index("pause_cron"), self.steps.index("stop_runtime"))
        self.assertLess(self.steps.index("stop_runtime"), self.steps.index("ensure_checkout"))
        self.assertLess(self.steps.index("run_django_release"), self.steps.index("restart_mcp_runtime"))
        self.assertLess(self.steps.index("run_django_release"), self.steps.index("restart_web"))
        self.assertEqual(self.steps[-3:], ["public_smoke", "verify_revision", "resume_cron"])
        self.assertFalse(self.cron_paused)

    def test_migration_failure_keeps_runtime_and_cron_stopped(self):
        deploy.run_django_release.side_effect = RuntimeError("migration failed")
        with self.assertRaisesRegex(RuntimeError, "migration failed"):
            deploy.deploy.body(None)
        self.assertTrue(self.cron_paused)
        self.assertEqual(self.steps[-1], "stop_runtime")
        deploy.restart_mcp_runtime.assert_not_called()
        deploy.restart_web.assert_not_called()

    def test_failed_health_after_restart_stops_runtime_again(self):
        deploy.public_smoke.side_effect = RuntimeError("unhealthy")
        with self.assertRaisesRegex(RuntimeError, "unhealthy"):
            deploy.deploy.body(None)
        self.assertIn("restart_web", self.steps)
        self.assertEqual(self.steps[-1], "stop_runtime")
        self.assertTrue(self.cron_paused)

    def test_unrecovered_release_blocks_checkout_changes(self):
        self.cron_paused = True
        with self.assertRaisesRegex(RuntimeError, "previous release left cron paused"):
            deploy.deploy.body(None)
        deploy.prepare_release.assert_not_called()
        deploy.ensure_checkout.assert_not_called()
        self.assertTrue(self.cron_paused)


if __name__ == "__main__":
    main()
