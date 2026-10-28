"""Packaging acceptance tests (AC14).

Builds a wheel with ``pip wheel . --no-build-isolation``, installs it into a
fresh virtual environment and verifies the importable package, the installed
``hone`` console script and ``python -m hone`` entry point.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _venv_script(venv: Path, name: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / (name + ".exe")
    return venv / "bin" / name


def _clean_env() -> dict:
    """Environment without ``PYTHONPATH``/``PYTHONHOME`` leaks from the caller.

    A leaking ``PYTHONPATH`` would put the source checkout on the virtual
    environment's ``sys.path``; the generated ``hone.egg-info`` would then make
    pip believe hone is already installed and skip the wheel installation.
    """

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


class TestPackaging(unittest.TestCase):
    def test_wheel_build_install_and_entrypoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dist = tmp_path / "dist"
            build = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-build-isolation",
                    "--no-deps",
                    "-w",
                    str(dist),
                ],
                cwd=str(ROOT),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                build.returncode, 0, build.stdout.decode("utf-8", "replace")
            )
            wheels = sorted(dist.glob("hone-*.whl"))
            self.assertEqual(len(wheels), 1, list(dist.iterdir()))
            wheel = wheels[0]

            # The wheel must contain the package (incl. hone.utils) but not the
            # public fixtures or docs.
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
            self.assertIn("hone/__init__.py", names)
            self.assertIn("hone/hone.py", names)
            self.assertIn("hone/__main__.py", names)
            self.assertTrue(any(name.startswith("hone/utils/") for name in names))
            self.assertFalse(any(name.startswith("docs/") for name in names))
            self.assertFalse(any(name.startswith("data_file/") for name in names))
            self.assertFalse(any(name.startswith("examples/") for name in names))

            venv = tmp_path / "venv"
            create = subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                create.returncode, 0, create.stdout.decode("utf-8", "replace")
            )
            vpython = _venv_python(venv)
            install = subprocess.run(
                [
                    str(vpython),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--force-reinstall",
                    str(wheel),
                ],
                cwd=str(tmp_path),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                install.returncode, 0, install.stdout.decode("utf-8", "replace")
            )

            # Run outside the repo so the local source tree cannot shadow the
            # installed package.
            check_import = subprocess.run(
                [
                    str(vpython),
                    "-c",
                    "import hone; from hone.hone import Hone; "
                    "print(hone.Hone is Hone)",
                ],
                cwd=str(tmp_path),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                check_import.returncode, 0, check_import.stdout.decode("utf-8", "replace")
            )
            self.assertIn(b"True", check_import.stdout)

            help_script = subprocess.run(
                [str(_venv_script(venv, "hone")), "--help"],
                cwd=str(tmp_path),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                help_script.returncode, 0, help_script.stdout.decode("utf-8", "replace")
            )
            self.assertIn(b"csv_filepath", help_script.stdout)

            help_module = subprocess.run(
                [str(vpython), "-m", "hone", "--help"],
                cwd=str(tmp_path),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                help_module.returncode, 0, help_module.stdout.decode("utf-8", "replace")
            )
            self.assertIn(b"csv_filepath", help_module.stdout)

            # End to end conversion from the installed package.
            csv_path = tmp_path / "in.csv"
            csv_path.write_text("a,a_b,b_c\n1,2,3\n", encoding="utf-8")
            out_path = tmp_path / "out.json"
            convert = subprocess.run(
                [str(_venv_script(venv, "hone")), str(csv_path), str(out_path)],
                cwd=str(tmp_path),
                env=_clean_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(
                convert.returncode, 0, convert.stdout.decode("utf-8", "replace")
            )
            # ``b_c`` has no sibling sharing the ``b_`` prefix, so it stays flat.
            self.assertEqual(
                json.loads(out_path.read_text(encoding="utf-8")),
                [{"a": "1", "a_b": "2", "b_c": "3"}],
            )


if __name__ == "__main__":
    unittest.main()
