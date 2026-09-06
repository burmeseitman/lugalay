"""Security and lifecycle tests for the Gemini key settings flow."""

import json
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bus
import setup as setup_mod


class TestGeminiKeySettings(unittest.TestCase):

    def test_key_is_stored_once_and_never_returned(self):
        cfg = {"tts": {"api_key": "legacy-key"}}
        result = setup_mod.set_gemini_api_key(cfg, "new-secret-key")

        self.assertTrue(result)
        self.assertEqual(cfg["tts"]["gemini_api_key"], "new-secret-key")
        self.assertEqual(cfg["tts"]["api_key"], "")
        self.assertNotIn("new-secret-key", repr(result))

    def test_key_with_whitespace_is_rejected(self):
        with self.assertRaises(ValueError):
            setup_mod.set_gemini_api_key({"tts": {}}, "bad key")

    def test_remove_clears_current_and_legacy_fields(self):
        cfg = {"tts": {"gemini_api_key": "new", "api_key": "legacy"}}
        setup_mod.set_gemini_api_key(cfg, clear=True)
        self.assertNotIn("gemini_api_key", cfg["tts"])
        self.assertEqual(cfg["tts"]["api_key"], "")

    def test_config_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with patch.object(bus, "CONFIG", path):
                bus.save_config({"tts": {"gemini_api_key": "secret"}})

            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["tts"]["gemini_api_key"], "secret")

    def test_bus_carries_validated_avatar_animation_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            with patch.object(bus, "BUS", path):
                payload = bus.write(
                    "speaking", "hello", .7, mouth="oh", expression="amused")
                self.assertEqual(payload["mouth"], "oh")
                self.assertEqual(payload["expression"], "amused")

                payload = bus.write(
                    "speaking", "hello", .7, mouth="invalid", expression="invalid")
                self.assertEqual(payload["mouth"], "closed")
                self.assertEqual(payload["expression"], "neutral")


if __name__ == "__main__":
    unittest.main()
