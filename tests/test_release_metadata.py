from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_project_declares_gpl_and_author(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(metadata["license"], "GPL-3.0-or-later")
        self.assertEqual(metadata["authors"], [{"name": "Gabriel Fraga da Fonseca"}])

    def test_canonical_license_and_installer_notice_are_present(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        installer_notice = (ROOT / "tools" / "installer" / "START HERE.txt").read_text(
            encoding="utf-8"
        )
        assembler = (ROOT / "tools" / "assemble_windows_release.py").read_text(
            encoding="utf-8"
        )
        normalized_notice = " ".join(installer_notice.split())
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3, 29 June 2007", license_text)
        self.assertIn("Copyright (C) 2026 Gabriel Fraga da Fonseca", normalized_notice)
        self.assertIn("GNU General Public License version 3 or later", normalized_notice)
        self.assertIn("root / 'LICENSE'", assembler)


if __name__ == "__main__":
    unittest.main()
