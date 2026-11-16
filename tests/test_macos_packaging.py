"""Regression checks for the Apple Silicon macOS packaging contract."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MacOSPackagingTests(unittest.TestCase):
    def test_macos_build_script_uses_python_module_pyinstaller(self) -> None:
        script = ROOT / "tools" / "build_macos_bundle.sh"

        self.assertTrue(script.is_file())
        self.assertIn("python -m PyInstaller", script.read_text(encoding="utf-8"))

    def test_macos_spec_builds_an_app_bundle_without_windows_dll_logic(self) -> None:
        spec = ROOT / "tools" / "marine_drift_macos.spec"

        self.assertTrue(spec.is_file())
        contents = spec.read_text(encoding="utf-8")
        self.assertIn("BUNDLE(", contents)
        self.assertIn('tools/installer/app.icns', contents)
        self.assertTrue((ROOT / "tools" / "installer" / "app.icns").is_file())
        self.assertNotIn(".dll", contents.lower())

    def test_macos_verifier_targets_the_app_executable(self) -> None:
        verifier = ROOT / "tools" / "verify_macos_bundle.py"

        self.assertTrue(verifier.is_file())
        self.assertIn(
            "Contents/MacOS/Marine Drift Workbench",
            verifier.read_text(encoding="utf-8"),
        )

    def test_macos_verifier_exercises_all_production_workers(self) -> None:
        verifier = ROOT / "tools" / "verify_macos_bundle.py"
        contents = verifier.read_text(encoding="utf-8")

        self.assertIn("production-example", contents)
        self.assertIn("Production reverse-drift worker verified", contents)
        self.assertIn("Frozen results worker succeeded", contents)
        self.assertIn('for operation in ("inspect", "export", "map")', contents)


if __name__ == "__main__":
    unittest.main()
