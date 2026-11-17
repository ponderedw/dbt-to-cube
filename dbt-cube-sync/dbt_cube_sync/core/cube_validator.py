"""
Cube.js schema validator — spins up Cube.js via Docker and runs test queries.

Used by the `validate-cubes` CLI command for pre-merge CI validation.
"""
import json
import random
import string
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests


@dataclass
class CubeValidationResult:
    cube_name: str
    passed: bool
    measures_tested: List[str] = field(default_factory=list)
    dimensions_found: int = 0
    failed_query: Optional[dict] = None
    error: Optional[str] = None
    cube_logs_snippet: Optional[str] = None


class CubeValidator:
    """Orchestrates a temporary Cube.js Docker container and validates loaded schemas."""

    def __init__(
        self,
        output_dir: str,
        db_config: Dict[str, str],
        cube_image: str = "cubejs/cube:latest",
        port: int = 4100,
        startup_timeout: int = 180,
        query_timeout: int = 60,
    ):
        self.output_dir = Path(output_dir).resolve()
        self.db_config = db_config
        self.cube_image = cube_image
        self.port = port
        self.startup_timeout = startup_timeout
        self.query_timeout = query_timeout
        self.base_url = f"http://localhost:{port}"
        self._container_name: Optional[str] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the Cube.js container."""
        self._container_name = "cube-ci-" + "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        self._write_cube_config()

        env_args: List[str] = []
        for key, value in self.db_config.items():
            if value is not None:
                env_args += ["-e", f"{key}={value}"]

        cmd = [
            "docker", "run", "-d",
            "--name", self._container_name,
            "-p", f"{self.port}:4000",
            "-v", f"{self.output_dir}:/cube/conf",
            *env_args,
            self.cube_image,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start Cube.js container:\n{result.stderr.strip()}"
            )

    def stop(self) -> None:
        """Remove the container (best-effort cleanup)."""
        if self._container_name:
            subprocess.run(
                ["docker", "rm", "-f", self._container_name],
                capture_output=True,
            )
            self._container_name = None

    def wait_ready(self) -> None:
        """Poll /readyz until Cube.js is accepting requests."""
        deadline = time.time() + self.startup_timeout
        last_err = ""
        while time.time() < deadline:
            try:
                r = requests.get(f"{self.base_url}/readyz", timeout=3)
                if r.status_code == 200:
                    return
            except requests.RequestException as e:
                last_err = str(e)
            time.sleep(3)
        logs = self._container_logs(last_n_lines=40)
        raise TimeoutError(
            f"Cube.js did not become ready within {self.startup_timeout}s.\n"
            f"Last error: {last_err}\n\nContainer logs:\n{logs}"
        )

    # ── Validation ────────────────────────────────────────────────────────────

    def get_meta(self) -> dict:
        """Fetch /cubejs-api/v1/meta and return parsed JSON."""
        r = requests.get(f"{self.base_url}/cubejs-api/v1/meta", timeout=15)
        r.raise_for_status()
        return r.json()

    def validate_all(self, meta: dict) -> List[CubeValidationResult]:
        """Run a test query against each cube and return results."""
        results: List[CubeValidationResult] = []
        for cube in meta.get("cubes", []):
            result = self._validate_cube(cube)
            results.append(result)
        return results

    def _validate_cube(self, cube: dict) -> CubeValidationResult:
        name = cube["name"]
        measures = [m["name"] for m in cube.get("measures", [])]
        dimensions = [d["name"] for d in cube.get("dimensions", [])]

        if not measures and not dimensions:
            return CubeValidationResult(
                cube_name=name,
                passed=True,
                dimensions_found=0,
            )

        # Pick the first measure for the test query; fall back to dimension
        if measures:
            query = {"measures": [measures[0]], "dimensions": [], "limit": 1}
            tested = [measures[0]]
        else:
            query = {"measures": [], "dimensions": [dimensions[0]], "limit": 1}
            tested = [dimensions[0]]

        error, logs_snippet = self._run_query(query)
        if error:
            return CubeValidationResult(
                cube_name=name,
                passed=False,
                measures_tested=tested,
                dimensions_found=len(dimensions),
                failed_query=query,
                error=error,
                cube_logs_snippet=logs_snippet,
            )
        return CubeValidationResult(
            cube_name=name,
            passed=True,
            measures_tested=tested,
            dimensions_found=len(dimensions),
        )

    def _run_query(self, query: dict):
        """Execute a /load query, retrying through 'Continue wait', return (error, logs)."""
        payload = {"query": query}
        deadline = time.time() + self.query_timeout
        while time.time() < deadline:
            try:
                r = requests.post(
                    f"{self.base_url}/cubejs-api/v1/load",
                    json=payload,
                    timeout=20,
                )
                data = r.json()
                err = data.get("error", "")
                if err == "Continue wait":
                    time.sleep(2)
                    continue
                if err:
                    logs = self._container_logs(last_n_lines=20)
                    return err, logs
                return None, None
            except requests.RequestException as e:
                return str(e), None
        return f"Query timed out after {self.query_timeout}s", None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _container_logs(self, last_n_lines: int = 30) -> str:
        if not self._container_name:
            return ""
        result = subprocess.run(
            ["docker", "logs", "--tail", str(last_n_lines), self._container_name],
            capture_output=True,
            text=True,
        )
        return (result.stdout + result.stderr).strip()

    def _write_cube_config(self) -> None:
        """Write a minimal cube.js config to the output dir for the test run."""
        cfg_path = self.output_dir / "cube.js"
        if not cfg_path.exists():
            cfg_path.write_text(
                'module.exports = {\n'
                '  schemaPath: "model/cubes",\n'
                '  schemaVersion: () => "ci-test",\n'
                '};\n'
            )


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_validation_report(results: List[CubeValidationResult]) -> bool:
    """Print a clear validation report. Returns True if all passed."""
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    total = len(results)

    _hr("═")
    print("CUBE VALIDATION RESULTS")
    _hr("═")
    print()

    for r in results:
        icon = "✓" if r.passed else "✗"
        measures_info = (
            f"  ({len(r.measures_tested)} measure(s) tested, {r.dimensions_found} dim(s))"
            if r.passed and r.measures_tested
            else ""
        )
        status = "PASSED" if r.passed else "FAILED"
        print(f"  {icon} {r.cube_name:40s}  {status}{measures_info}")

    if failed:
        print()
        _hr("─")
        print(f"FAILURES ({len(failed)})")
        _hr("─")
        for r in failed:
            print()
            print(f"  Cube:   {r.cube_name}")
            if r.failed_query:
                print(f"  Query:  {json.dumps(r.failed_query)}")
            if r.error:
                # Indent multiline error
                for line in r.error.splitlines():
                    print(f"  Error:  {line}")
            if r.cube_logs_snippet:
                print("  Cube.js logs (last 20 lines):")
                for line in r.cube_logs_snippet.splitlines()[-10:]:
                    print(f"    {line}")

    print()
    _hr("═")
    result_line = (
        f"RESULT: {len(passed)}/{total} passed"
        + (f", {len(failed)} FAILED" if failed else "")
    )
    print(result_line)
    _hr("═")

    return len(failed) == 0


def _hr(char: str = "─", width: int = 62) -> None:
    print(char * width)
