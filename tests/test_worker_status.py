import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from sparecore.worker_status import _guest_summary, _host_summary, _run, snapshot


def machine(status="Stopped", cpu=2, mem=2147483648, host_loopback=False, name="worker-a"):
    return {
        "name": name, "status": status, "vmType": "vz",
        "arch": "aarch64", "cpus": cpu, "memory": mem, "disk": 20 * 1024**3,
        "config": {"plain": True, "mounts": None,
                   "networkOpts": {"hostLoopback": host_loopback},
                   "ssh": {"forwardAgent": False}}
    }


class WorkerReadOnlyTests(unittest.TestCase):
    @patch("sparecore.worker_status.subprocess.run")
    def test_subprocess_consumes_no_caller_stdin(self, run):
        run.return_value.stdout = "ok"
        self.assertEqual(_run(["/bin/echo", "ok"]), "ok")
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    @patch("sparecore.worker_status._run")
    def test_vm_parses_exact_machine(self, run):
        run.return_value = json.dumps(machine())
        self.assertEqual(_guest_summary("worker-a")["vm"], "stopped")
        self.assertTrue(_guest_summary("worker-a")["isolation_verified"])

    @patch("sparecore.worker_status._run")
    def test_vm_rejects_excessive_ram(self, run):
        run.return_value = json.dumps(machine(mem=8 * 1024**3))
        self.assertFalse(_guest_summary("worker-a")["isolation_verified"])

    @patch("sparecore.worker_status._run")
    def test_vm_rejects_host_loopback(self, run):
        run.return_value = json.dumps(machine(host_loopback=True))
        self.assertFalse(_guest_summary("worker-a")["isolation_verified"])

    @patch("sparecore.worker_status._run")
    def test_vm_missing_is_unknown(self, run):
        run.return_value = json.dumps({"name": "worker-b"})
        self.assertEqual(_guest_summary("worker-a")["vm"], "unknown")

    @patch("sparecore.worker_status._run")
    def test_vm_cli_failure_is_unknown(self, run):
        run.return_value = None
        self.assertEqual(_guest_summary("worker-a")["vm"], "unknown")


    @patch("sparecore.worker_status._run")
    def test_unspecified_vm_does_not_query_inventory(self, run):
        self.assertEqual(_guest_summary()["vm"], "unknown")
        run.assert_not_called()

    @patch("sparecore.worker_status._run")
    def test_selects_second_vm_from_same_inventory(self, run):
        run.return_value = "\n".join([json.dumps(machine(name="worker-a")),
                                       json.dumps(machine(name="worker-b"))])
        result = _guest_summary("worker-b")
        self.assertTrue(result["isolation_verified"])
        self.assertEqual(result["name"], "worker-b")
        self.assertEqual(_guest_summary("worker-c")["vm"], "unknown")

    @patch("sparecore.worker_status._run")
    def test_lima_names_with_dots_underscores_and_uppercase(self, run):
        for name in ("Ubuntu-20.04", "example.com", "under_score"):
            run.return_value = json.dumps(machine(name=name))
            self.assertEqual(_guest_summary(name)["name"], name)

    @patch("sparecore.worker_status._run")
    def test_invalid_vm_name_fails_without_command(self, run):
        self.assertEqual(_guest_summary("--bad")["vm"], "unknown")
        run.assert_not_called()

    @patch("sparecore.worker_status._run")
    def test_host_disallows_stale_reading(self, run):
        run.side_effect = ["Now drawing from 'AC Power'", "1", "boost\tOK\t120"]
        self.assertEqual(_host_summary()["tier"], "off")

    @patch("sparecore.worker_status._run")
    def test_host_disallows_battery_even_on_boost(self, run):
        run.side_effect = ["Now drawing from 'Battery Power'", "1", "boost\tOK\t3"]
        self.assertEqual(_host_summary()["tier"], "off")

    @patch("sparecore.worker_status._run")
    def test_host_reads_recent_status(self, run):
        run.side_effect = ["Now drawing from 'AC Power'", "1", "boost\tOK\t3"]
        self.assertEqual(_host_summary()["tier"], "boost")

    @patch("sparecore.worker_status.platform.system", return_value="Linux")
    def test_non_mac_is_readonly(self, _):
        self.assertFalse(snapshot()["applied"])

    def test_worker_plan_json_cli(self):
        data = {"tier": "boost", "vm": "stopped", "node_ready": None,
                "node_cordoned": True, "workloads": 0, "enabled": True}
        out = subprocess.check_output([
            sys.executable, "-m", "sparecore", "worker",
            "--input", json.dumps(data)], text=True)
        result = json.loads(out)
        self.assertEqual(result["step"], "start_vm")
        self.assertFalse(result["applied"])


    def test_worker_cli_rejects_explicit_empty_input_conflict(self):
        result = subprocess.run([sys.executable, "-m", "sparecore", "worker",
                                 "--vm", "worker-b", "--input", ""],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--vm is supported", result.stderr)

    def test_worker_cli_with_vm_is_read_only(self):
        out = subprocess.check_output([
            sys.executable, "-m", "sparecore", "worker", "--vm", "worker-b"],
            text=True)
        result = json.loads(out)
        self.assertFalse(result["applied"])
        self.assertIn("no kubeconfig", result["cluster"])

    def test_worker_inspect_never_requires_kubeconfig(self):
        out = subprocess.check_output([
            sys.executable, "-m", "sparecore", "worker"], text=True)
        result = json.loads(out)
        self.assertEqual(result["applied"], False)
        self.assertIn("no kubeconfig", result["cluster"])


if __name__ == "__main__":
    unittest.main()
