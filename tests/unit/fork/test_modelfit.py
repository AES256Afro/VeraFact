# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,missing-class-docstring,missing-function-docstring

import json
from unittest import mock

from parameterized import parameterized

from searx.fork import modelfit
from searx.fork.modelfit import hardware
from tests import SearxTestCase

CPUINFO = """processor\t: 0
vendor_id\t: AuthenticAMD
model name\t: AMD Ryzen 9 7900 12-Core Processor
flags\t\t: fpu vme sse4_2 avx avx2 avx512f amx_tile
processor\t: 1
model name\t: AMD Ryzen 9 7900 12-Core Processor
flags\t\t: fpu avx2
"""

MEMINFO = """MemTotal:       31251484 kB
MemFree:         9000000 kB
MemAvailable:   25000000 kB
"""

NVIDIA = "NVIDIA GeForce RTX 4070, 12282, 512\n"
ROCM = json.dumps(
    {
        "card0": {
            "VRAM Total Memory (B)": "17163091968",
            "VRAM Total Used Memory (B)": "1073741824",
            "Card series": "Radeon RX 7800 XT",
        }
    }
)
PROFILER = """Hardware:
    Hardware Overview:
      Chip: Apple M2 Pro
      Total Number of Cores: 12 (8 performance and 4 efficiency)
      Memory: 32 GB
"""


class ParsersTest(SearxTestCase):

    def test_cpuinfo(self):
        cpu = hardware.parse_cpuinfo(CPUINFO)
        self.assertEqual(cpu["cpu_model"], "AMD Ryzen 9 7900 12-Core Processor")
        self.assertEqual(cpu["cores"], 2)
        self.assertEqual(cpu["flags"], ["amx_tile", "avx2", "avx512f", "sse4_2"])

    def test_meminfo(self):
        mem = hardware.parse_meminfo(MEMINFO)
        self.assertAlmostEqual(mem["mem_total_gb"], 29.8, places=1)
        self.assertAlmostEqual(mem["mem_available_gb"], 23.84, places=1)
        self.assertEqual(hardware.parse_meminfo("garbage"), {"mem_total_gb": 0.0, "mem_available_gb": 0.0})

    def test_nvidia(self):
        gpus = hardware.parse_nvidia_smi(NVIDIA + "\n, , \n")
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, "nvidia")
        self.assertEqual(gpus[0].name, "NVIDIA GeForce RTX 4070")
        self.assertAlmostEqual(gpus[0].vram_gb, 11.99, places=1)
        self.assertAlmostEqual(gpus[0].used_gb, 0.5, places=1)

    def test_rocm(self):
        gpus = hardware.parse_rocm_smi(ROCM)
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, "amd")
        self.assertEqual(gpus[0].name, "Radeon RX 7800 XT")
        self.assertAlmostEqual(gpus[0].vram_gb, 15.98, places=1)
        self.assertEqual(hardware.parse_rocm_smi("not json"), [])

    def test_system_profiler(self):
        apple = hardware.parse_system_profiler(PROFILER)
        self.assertEqual(apple, {"cpu_model": "Apple M2 Pro", "cores": 12, "mem_total_gb": 32.0})

    def test_override(self):
        hw = hardware.parse_override(
            json.dumps(
                {
                    "cpu": {"model": "x", "cores": 4, "flags": ["avx2"]},
                    "memory": {"total_gb": 16, "available_gb": 12},
                    "gpus": [{"vendor": "nvidia", "name": "T4", "vram_gb": 16}],
                    "bandwidth_gbs": 40,
                }
            )
        )
        self.assertIsNotNone(hw)
        self.assertEqual(hw.cores, 4)
        self.assertEqual(hw.gpus[0].vram_gb, 16.0)
        self.assertEqual(hw.bandwidth_gbs, 40.0)
        self.assertEqual(hw.sources, ["override file"])
        self.assertIsNone(hardware.parse_override("[]"))
        self.assertIsNone(hardware.parse_override("{"))

    def test_override_wins(self):
        with mock.patch.object(
            hardware,
            "_read",
            side_effect=lambda p: '{"memory": {"total_gb": 8}}' if p.endswith("hardware.json") else "",
        ):
            hw = hardware.read_hardware()
        self.assertEqual(hw.mem_total_gb, 8.0)
        self.assertEqual(hw.sources, ["override file"])

    def test_read_hardware_from_proc(self):
        files = {"/proc/cpuinfo": CPUINFO, "/proc/meminfo": MEMINFO}
        with (
            mock.patch.object(hardware, "_read", side_effect=lambda p: files.get(p, "")),
            mock.patch.object(
                hardware, "_run", side_effect=lambda cmd, timeout=5.0: NVIDIA if cmd[0] == "nvidia-smi" else ""
            ),
            mock.patch("platform.system", return_value="Linux"),
        ):
            hw = hardware.read_hardware()
        self.assertEqual(hw.cores, 2)
        self.assertAlmostEqual(hw.mem_total_gb, 29.8, places=1)
        self.assertEqual(len(hw.gpus), 1)
        self.assertEqual(hw.sources, ["/proc/cpuinfo", "/proc/meminfo", "nvidia-smi"])


class ArithmeticTest(SearxTestCase):

    def test_weights(self):
        self.assertEqual(modelfit.weight_gb(8, "Q4_K_M"), 4.8)
        self.assertEqual(modelfit.weight_gb(3, "Q8_0"), 3.21)
        self.assertEqual(modelfit.weight_gb(7, "unknown"), 4.2)

    def test_kv_cache(self):
        # Llama-3-8B shape: ~131 KB/token, 8k ≈ 1 GB
        self.assertAlmostEqual(modelfit.kv_cache_gb(8192), 1.0, places=1)
        self.assertAlmostEqual(modelfit.kv_cache_gb(8192, layers=32, kv_heads=32), 4.0, places=1)

    def test_speed(self):
        self.assertEqual(modelfit.tokens_per_second(40, modelfit.weight_gb(3)), 22.2)
        self.assertEqual(modelfit.tokens_per_second(None, 4.8), 6.2)
        self.assertIsNone(modelfit.tokens_per_second(40, 0))

    def test_budget(self):
        cpu = hardware.Hardware(mem_total_gb=32, mem_available_gb=28)
        self.assertEqual(modelfit.budget_gb(cpu), (22.4, "cpu"))  # 70 % cap wins over 28 - 3
        small = hardware.Hardware(mem_total_gb=8, mem_available_gb=5)
        self.assertEqual(modelfit.budget_gb(small), (2.0, "cpu"))
        gpu = hardware.Hardware(mem_total_gb=64, gpus=[hardware.Gpu(vendor="nvidia", name="x", vram_gb=12)])
        self.assertEqual(modelfit.budget_gb(gpu), (11.2, "gpu"))
        apple = hardware.Hardware(mem_total_gb=32, apple_unified=True)
        self.assertEqual(modelfit.budget_gb(apple), (22.4, "apple"))


class TiersTest(SearxTestCase):

    @parameterized.expand(
        [
            (hardware.Hardware(mem_total_gb=8, mem_available_gb=6), "under 8 GB", 1.5),
            (hardware.Hardware(mem_total_gb=16, mem_available_gb=13), "8–16 GB", 3.0),
            (hardware.Hardware(mem_total_gb=32, mem_available_gb=26), "16–32 GB", 3.0),
            (hardware.Hardware(mem_total_gb=64, mem_available_gb=60), "32 GB of RAM or more", 8.0),
            (hardware.Hardware(mem_total_gb=32, gpus=[hardware.Gpu(vendor="nvidia", vram_gb=6)]), "6 GB GPU", 3.0),
            (hardware.Hardware(mem_total_gb=32, gpus=[hardware.Gpu(vendor="nvidia", vram_gb=8)]), "8 GB GPU", 8.0),
            (hardware.Hardware(mem_total_gb=32, gpus=[hardware.Gpu(vendor="nvidia", vram_gb=12)]), "12 GB GPU", 14.0),
            (hardware.Hardware(mem_total_gb=32, gpus=[hardware.Gpu(vendor="nvidia", vram_gb=16)]), "16 GB GPU", 14.0),
            (hardware.Hardware(mem_total_gb=32, gpus=[hardware.Gpu(vendor="nvidia", vram_gb=24)]), "24 GB GPU", 32.0),
            (hardware.Hardware(mem_total_gb=16, apple_unified=True), "Apple silicon with 16 GB", 8.0),
            (hardware.Hardware(mem_total_gb=64, apple_unified=True), "Apple silicon with 32–64 GB", 14.0),
        ]
    )
    def test_tiers(self, box, tier_fragment, params_b):
        rec = modelfit.recommend(box)
        self.assertIn(tier_fragment, rec.tier)
        self.assertEqual(rec.params_b, params_b)
        self.assertTrue(rec.suggest)
        self.assertTrue(rec.notes)
        self.assertEqual(len(rec.checklist), 7)

    def test_cpu_notes(self):
        rec = modelfit.recommend(hardware.Hardware(mem_total_gb=32, mem_available_gb=26, flags=["sse4_2"]))
        self.assertEqual(rec.where, "cpu")
        self.assertIsNotNone(rec.tokens_per_s)
        self.assertTrue(any("bandwidth unknown" in n for n in rec.notes))
        self.assertTrue(any("No AVX2" in n for n in rec.notes))


class ReportTest(SearxTestCase):

    def setUp(self):
        super().setUp()
        modelfit._CACHE.clear()  # pylint: disable=protected-access

    def test_report_is_cached(self):
        hw = hardware.Hardware(mem_total_gb=16, mem_available_gb=12, sources=["test"])
        with mock.patch.object(modelfit, "read_hardware", return_value=hw) as read:
            first = modelfit.report()
            second = modelfit.report()
            self.assertIs(first, second)
            self.assertEqual(read.call_count, 1)
            modelfit.report(force=True)
            self.assertEqual(read.call_count, 2)
        self.assertEqual(first["hardware"]["mem_total_gb"], 16.0)
        self.assertIn("recommendation", first)

    def test_json_route_and_preferences(self):
        hw = hardware.Hardware(cpu_model="Test CPU", cores=4, mem_total_gb=16, mem_available_gb=12, sources=["test"])
        with mock.patch.object(modelfit, "read_hardware", return_value=hw):
            resp = self.client.get("/fork/modelfit.json")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["hardware"]["cpu_model"], "Test CPU")
            self.assertIn("8–16 GB", data["recommendation"]["tier"])
            page = self.client.get("/preferences")
            self.assertIn(b'id="pref_fork_modelfit"', page.data)
            self.assertIn("8–16 GB".encode(), page.data)
