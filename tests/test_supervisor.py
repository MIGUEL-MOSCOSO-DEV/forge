import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from forge.cli import main
from forge.supervisor import environment, listening, load_config, order, validate


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "forge.toml"

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, body):
        self.config.write_text(body, encoding="utf-8")

    def test_command_requires_argument_list(self):
        self.write('[services.api]\ncommand="unsafe shell string"\n')
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_dependencies_are_topologically_ordered(self):
        self.assertEqual(order({"api": {"depends_on": ["db"]}, "db": {}}), ["db", "api"])
        with self.assertRaises(ValueError):
            order({"a": {"depends_on": ["b"]}, "b": {"depends_on": ["a"]}})

    def test_unknown_dependency_rejected(self):
        self.write('[services.api]\ncommand=["python"]\ndepends_on=["missing"]\n')
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_duplicate_ports_rejected(self):
        self.write(
            '[services.a]\ncommand=["python"]\nports=[45678]\n[services.b]\ncommand=["python"]\nports=[45678]\n'
        )
        with self.assertRaises(ValueError):
            load_config(self.config)

    def test_missing_environment_does_not_print_values(self):
        problems = validate({"api": {"required_env": ["NEEDED_SECRET"], "ports": []}}, {})
        self.assertEqual(problems, ["api: falta la variable NEEDED_SECRET"])

    def test_dotenv_does_not_override_existing_environment(self):
        (self.root / ".env").write_text("FORGE_TEST_VAR=from-file\n")
        previous = os.environ.get("FORGE_TEST_VAR")
        os.environ["FORGE_TEST_VAR"] = "existing"
        try:
            self.assertEqual(environment(self.root)["FORGE_TEST_VAR"], "existing")
        finally:
            if previous is None:
                os.environ.pop("FORGE_TEST_VAR")
            else:
                os.environ["FORGE_TEST_VAR"] = previous

    def test_port_conflict_is_detected(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            port = server.getsockname()[1]
            self.assertTrue(listening(port))
            self.assertTrue(validate({"api": {"ports": [port], "required_env": []}}, {}))

    def test_init_does_not_overwrite_existing_config(self):
        self.assertEqual(main(["--config", str(self.config), "init"]), 0)
        original = self.config.read_bytes()
        self.assertEqual(main(["--config", str(self.config), "init"]), 1)
        self.assertEqual(self.config.read_bytes(), original)

    def test_real_supervisor_logs_and_stops_owned_child(self):
        command = [
            sys.executable,
            "-u",
            "-c",
            "import time; print('service-ready',flush=True); time.sleep(30)",
        ]
        self.write("[services.worker]\ncommand=" + json.dumps(command) + "\n")
        process = subprocess.Popen(
            [sys.executable, "-m", "forge.cli", "--config", str(self.config), "up"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            state = self.root / ".forge" / "state.json"
            while not state.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(state.exists())
            (self.root / ".forge" / "stop").touch()
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr.decode())
            self.assertIn(b"running", stdout)
            self.assertIn("service-ready", (self.root / ".forge" / "worker.log").read_text())
            self.assertFalse(state.exists())
        finally:
            if process.poll() is None:
                (self.root / ".forge" / "stop").touch()
                process.communicate(timeout=10)
