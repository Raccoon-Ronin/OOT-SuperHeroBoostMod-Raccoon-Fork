"""Installer regressions using synthetic bytes only; no game or release payload.

Run: python -m unittest discover -s tests -v (requires zstandard, like the app).
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import installer as I
import recomp as R


def module_fixture(size=80):
    raw = bytearray(0x380)
    raw[:4] = b"NSO0"
    for index, (file_at, mem_at, length) in enumerate(((0x100, 0, 64), (0x200, 0x1000, 48),
                                                     (0x300, 0x2000, 128))):
        struct.pack_into("<III", raw, 0x10 + index * 16, file_at, mem_at, length)
        raw[file_at:file_at + length] = bytes([0x31 + index]) * length
    raw[0x310:0x318] = b"SHBCFG01"
    struct.pack_into("<II", raw, 0x318, 1, size)
    return I.patch_config(bytes(raw), I.Settings(button_mapping=False, manual_shield=True))


def image_fixture(module):
    image = bytearray(0x4000)
    for off in (0x10, 0x20, 0x30):
        file_at, mem_at, length = struct.unpack_from("<III", module, off)
        image[0x1000 + mem_at:0x1000 + mem_at + length] = module[file_at:file_at + length]
    return bytes(image)


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.exefs = self.game / ".hookshot_exefs"
        self.exefs.mkdir(parents=True)
        main = bytearray(0x100)
        main[:4] = b"NSO0"
        struct.pack_into("<I", main, 0x10, 0x100)
        main[0x40:0x60] = bytes.fromhex(I.BUILD_ID).ljust(32, b"\0")
        (self.exefs / "main").write_bytes(main)
        (self.game / "bin").mkdir()
        (self.game / "bin/hookshot.exe").write_bytes(b"synthetic stock executable")
        self.reference = module_fixture()
        self.payload = self.root / "payload"
        (self.payload / "standalone").mkdir(parents=True)
        (self.payload / "standalone/subsdk9").write_bytes(self.reference)
        (self.payload / "standalone/ours.ips").write_bytes(b"IPS32EEOF")
        (self.exefs / "subsdk9").write_bytes(self.reference)
        (self.game / "image.bin").write_bytes(image_fixture(self.reference))
        self.marker = self.game / "mods" / R.MOD_NAME / I.MARKER
        self.settings = I.Settings(button_mapping=False, manual_shield=True, hud_clock=True)
        for name, value in (("payload_dir", self.payload), ("_kill_game_copies", []), ("_game_processes", [])):
            mock = patch.object(R, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)
        R._built_cache.clear()
        R.backup_once(self.game)
        (self.game / "bin/hookshot.exe").write_bytes(b"synthetic rebuilt executable with module")

    def snapshot(self):
        return {p.relative_to(self.game).as_posix(): p.read_bytes()
                for p in self.game.rglob("*") if p.is_file()}

    def assert_rejected_without_writes(self):
        before = self.snapshot()
        with patch.object(R, "backup_once") as backup, patch.object(R, "build") as build:
            with self.assertRaises(I.InstallError):
                R.apply_settings(self.game, self.settings)
            backup.assert_not_called()
            build.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def assert_marker(self):
        meta = json.loads(self.marker.read_text(encoding="utf-8"))
        self.assertEqual(meta["variant"], "recomp")
        self.assertEqual(meta["module"], "standalone")
        self.assertEqual(meta["module_sha"], hashlib.sha256(self.reference).hexdigest())
        self.assertTrue(meta["manual_shield"])
        self.assertTrue(meta["hud_clock"])

    def test_code_only_install_then_apply_without_rebuild(self):
        def fake_build(*args, **kwargs):
            (self.game / "image.bin").write_bytes(image_fixture((self.exefs / "subsdk9").read_bytes()))
        builder = self.root / "builder"
        (builder / "tools/nx2").mkdir(parents=True)
        (builder / "tools/nx2/make_game.py").write_text("# synthetic builder")
        with patch.object(R, "build", side_effect=fake_build) as build:
            R.install(self.game, self.settings, builder_path=builder)
            self.assertEqual(build.call_count, 1)
            self.assert_marker()
            self.assertFalse((self.marker.parent / "romfs").exists())
            R.apply_settings(self.game, self.settings)
            self.assertEqual(build.call_count, 1)

    def test_romfs_install_and_transition_to_code_only(self):
        source = self.payload / "button_romfs/switch/UI"
        source.mkdir(parents=True)
        (source / "fixture.txt").write_text("synthetic texture placeholder")
        R.install_romfs(self.game, I.Settings(button_mapping=True))
        self.assertTrue((self.marker.parent / "romfs/UI/fixture.txt").exists())
        R.install_romfs(self.game, self.settings)
        self.assert_marker()
        self.assertFalse((self.marker.parent / "romfs").exists())

    def test_missing_metadata_recovers_configured_module_and_image(self):
        for size in (72, 76, 80):
            with self.subTest(size=size):
                self.reference = module_fixture(size)
                (self.payload / "standalone/subsdk9").write_bytes(self.reference)
                changed = I.patch_config(self.reference, I.Settings(button_mapping=False, clock_24h=True))
                (self.exefs / "subsdk9").write_bytes(changed)
                (self.game / "image.bin").write_bytes(image_fixture(changed))
                if self.marker.exists():
                    self.marker.unlink()
                with patch.object(R, "build") as build:
                    result = R.apply_settings(self.game, self.settings)
                    build.assert_not_called()
                self.assertFalse(result.rebuilt)
                self.assert_marker()
                self.assertEqual((self.exefs / "subsdk9").read_bytes(), I.patch_config(self.reference, self.settings))
                self.assertEqual((self.game / "image.bin").read_bytes(), image_fixture(I.patch_config(self.reference, self.settings)))

    def test_module_integrity_failures_do_not_write(self):
        for offset in (0x40, 0x100, 0x200, 0x300, 0x31D, 0x34D, 0x35F, 0x370):
            with self.subTest(offset=offset):
                data = bytearray(self.reference)
                data[offset] ^= 1
                (self.exefs / "subsdk9").write_bytes(data)
                self.assert_rejected_without_writes()

    def test_truncated_or_ambiguous_modules_do_not_write(self):
        for data in (self.reference[:-1], self.reference + b"SHBCFG01", b"SHBCFG01", b"unrelated module"):
            with self.subTest(data_length=len(data)):
                (self.exefs / "subsdk9").write_bytes(data)
                self.assert_rejected_without_writes()

    def test_image_integrity_failures_do_not_write(self):
        good = image_fixture(self.reference)
        for offset in (0x1000, 0x2000, 0x3000, 0x3018, 0x301C, 0x304D, 0x305F, 0x3070):
            with self.subTest(offset=offset):
                data = bytearray(good)
                data[offset] ^= 1
                (self.game / "image.bin").write_bytes(data)
                self.assert_rejected_without_writes()
        for data in (good[:0x3040], good + b"SHBCFG01", b"SHBCFG01", b"unrelated image"):
            with self.subTest(data_length=len(data)):
                (self.game / "image.bin").write_bytes(data)
                self.assert_rejected_without_writes()

    def test_missing_payload_or_image_do_not_write(self):
        for path in (self.payload / "standalone/subsdk9", self.game / "image.bin"):
            with self.subTest(path=path.name):
                saved = path.read_bytes()
                path.unlink()
                self.assert_rejected_without_writes()
                path.write_bytes(saved)

    def test_existing_invalid_metadata_is_not_recovered(self):
        self.marker.parent.mkdir(parents=True)
        for value in ("{", "null", "[]", "{}", json.dumps({"module": "relink", "module_sha": "wrong"}),
                      json.dumps({"module": "standalone", "module_sha": "wrong"})):
            with self.subTest(value=value):
                self.marker.write_text(value, encoding="utf-8")
                self.assert_rejected_without_writes()

    def test_wrong_build_and_incomplete_build_do_not_write(self):
        main = self.exefs / "main"
        original = main.read_bytes()
        for value in (original[:0x40], original[:0x40] + bytes(32),
                      original[:0x44] + b"\x01" * 28):
            with self.subTest(header_length=len(value)):
                main.write_bytes(value)
                self.assert_rejected_without_writes()
        main.write_bytes(original)
        with patch.object(R, "is_built", return_value=False):
            self.assert_rejected_without_writes()

    def test_existing_backup_contents_are_preserved(self):
        R.backup_once(self.game)
        backup = self.game / R.BACKUP
        before = {p.relative_to(backup): p.read_bytes() for p in backup.rglob("*") if p.is_file()}
        R.apply_settings(self.game, self.settings)
        after = {p.relative_to(backup): p.read_bytes() for p in backup.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_recovery_requires_backup_and_different_executable_contents(self):
        backup = self.game / R.BACKUP / "files/bin/hookshot.exe"
        original = backup.read_bytes()
        backup.unlink()
        self.assert_rejected_without_writes()
        backup.write_bytes(original)
        exe = self.game / "bin/hookshot.exe"
        exe.write_bytes(original)  # copied stock executable with a newer timestamp
        with patch.object(R, "is_built", return_value=True):
            self.assert_rejected_without_writes()

    def test_legacy_flat_executable_backup_can_recover(self):
        backup = self.game / R.BACKUP / "files/bin/hookshot.exe"
        backup.rename(self.game / R.BACKUP / "hookshot.exe")
        R.apply_settings(self.game, self.settings)
        self.assert_marker()

    def test_unsupported_payload_layouts_do_not_write(self):
        for offset, value in ((0x0C, 1), (0x318, 2), (0x31C, 84),
                              (0x18, 0xFFFFFFFF), (0x34, 0xFFFFFFFF), (0x38, 1)):
            with self.subTest(offset=offset, value=value):
                data = bytearray(self.reference)
                struct.pack_into("<I", data, offset, value)
                (self.payload / "standalone/subsdk9").write_bytes(data)
                (self.exefs / "subsdk9").write_bytes(data)
                self.assert_rejected_without_writes()

    def test_valid_metadata_does_not_allow_damaged_image(self):
        R.install_romfs(self.game, self.settings)
        (self.game / "image.bin").write_bytes(b"SHBCFG01")
        self.assert_rejected_without_writes()


if __name__ == "__main__":
    unittest.main()
