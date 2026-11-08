# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import pathlib

import msgspec
import yaml

from searx.fork.settings import SettingsFork
from tests import SearxTestCase

ROOT = pathlib.Path(__file__).resolve().parents[3]


class ContainerFilesTest(SearxTestCase):
    """The settings the container writes at first start, and the deployment
    files next to it, must be ones the app accepts."""

    def load(self, relative):
        with (ROOT / relative).open(encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_container_template(self):
        cfg = self.load("container/settings.template.yml")
        self.assertTrue(cfg["use_default_settings"])
        self.assertEqual(cfg["general"]["instance_name"], "VeraFact")
        fork = msgspec.convert(cfg["fork"], SettingsFork)
        self.assertEqual(fork.llm.backend, "disabled")
        self.assertEqual(fork.appearance.mark, "grid-check")

    def test_standalone_deploy_settings(self):
        cfg = self.load("deploy/verafact/config/settings.yml")
        self.assertEqual(cfg["general"]["instance_name"], "VeraFact")
        self.assertIn("json", cfg["search"]["formats"])
        msgspec.convert(cfg["fork"], SettingsFork)

    def test_dockerfile_healthcheck(self):
        dockerfile = (ROOT / "container/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("/healthz", dockerfile)

    def test_boxpilot_manifest_env(self):
        """Every FORK_* variable the manifest offers is one the settings read."""
        from searx.fork.settings import ENVIRON  # pylint: disable=import-outside-toplevel

        manifest = self.load("deploy/boxpilot/verafact.yaml")
        names = {entry["name"] for entry in manifest["env"]}
        for name in names:
            if name.startswith("FORK_"):
                self.assertIn(name, ENVIRON)
        self.assertIn("SEARXNG_SECRET", names)
        self.assertEqual(manifest["publicHostname"]["env"], "SEARXNG_BASE_URL")
        self.assertEqual(manifest["health"]["kind"], "healthcheck")
        self.assertEqual(manifest["defaultExposure"], "tailnet")
