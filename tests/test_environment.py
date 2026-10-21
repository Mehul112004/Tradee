"""Configuration contracts and Telegram CLI integration; no external sends."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tradee.c01 import ValidationError
from tradee.c14 import DeliveryResult
from tradee.cli import main
from tradee.environment import load_environment

TOKEN = "123456789:" + "a" * 30
OTHER = "987654321:" + "b" * 30
CHAT = -1001234567890


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ".env"

    def write(self, text):
        self.path.write_text(text)

    def test_missing_file_is_optional_and_never_created(self):
        settings = load_environment(self.path, {})
        self.assertEqual(settings.telegram_token, "")
        self.assertEqual(settings.operator_token, "")
        self.assertFalse(self.path.exists())

    def test_tbot_names_quotes_comments_and_negative_chat(self):
        self.write(f'export TELEGRAM_BOT_TOKEN="{TOKEN}" # existing bot\n'
                   f"TELEGRAM_CHAT_ID='{CHAT}'\nTRADEE_WEB_OPERATOR_TOKEN=operator-secret\n")
        env = load_environment(self.path, {})
        self.assertEqual(env.telegram_token, TOKEN)
        self.assertEqual(env.telegram_chat_id, str(CHAT))
        self.assertEqual(env.operator_token, "operator-secret")

    def test_exported_alias_beats_file_canonical_token(self):
        self.write(f'TRADEE_TELEGRAM_BOT_TOKEN={TOKEN}\n')
        self.assertEqual(load_environment(self.path, {"TELEGRAM_BOT_TOKEN": OTHER}).telegram_token, OTHER)

    def test_canonical_name_wins_within_each_source(self):
        self.write(f'TELEGRAM_BOT_TOKEN={TOKEN}\nTRADEE_TELEGRAM_BOT_TOKEN={OTHER}\n')
        self.assertEqual(load_environment(self.path, {}).telegram_token, OTHER)
        self.assertEqual(load_environment(self.path, {
            "TELEGRAM_BOT_TOKEN": OTHER, "TRADEE_TELEGRAM_BOT_TOKEN": TOKEN,
        }).telegram_token, TOKEN)

    def test_empty_export_explicitly_disables_file_secret(self):
        self.write(f'TELEGRAM_BOT_TOKEN={TOKEN}\nTRADEE_WEB_OPERATOR_TOKEN=file-secret\n')
        env = load_environment(self.path, {"TELEGRAM_BOT_TOKEN": "", "TRADEE_WEB_OPERATOR_TOKEN": ""})
        self.assertEqual(env.telegram_token, "")
        self.assertEqual(env.operator_token, "")

    def test_disabled_loader_does_not_read_but_keeps_exports(self):
        self.write(f'TELEGRAM_BOT_TOKEN={OTHER}\n')
        with patch("pathlib.Path.open", side_effect=AssertionError("No file read")):
            env = load_environment(self.path, {
                "PYTHON_DOTENV_DISABLED": "true", "TELEGRAM_BOT_TOKEN": TOKEN,
            })
        self.assertEqual(env.telegram_token, TOKEN)

    def test_root_resolution_does_not_search_current_or_parent_directories(self):
        self.write(f'TELEGRAM_BOT_TOKEN={TOKEN}\n')
        with patch("tradee.environment.ROOT_ENV", self.path), patch("pathlib.Path.cwd", side_effect=AssertionError):
            self.assertEqual(load_environment(environ={}).telegram_token, TOKEN)

    def test_no_interpolation_shell_execution_or_process_mutation(self):
        self.write('TELEGRAM_BOT_TOKEN=${SECRET}\nTRADEE_WEB_OPERATOR_TOKEN=$(echo private)\nDATABASE_URL=unrelated\n')
        before = dict(os.environ)
        env = load_environment(self.path, {"SECRET": "do-not-expand"})
        self.assertEqual(env.telegram_token, "${SECRET}")
        self.assertEqual(env.operator_token, "$(echo private)")
        self.assertFalse(hasattr(env, "DATABASE_URL"))
        self.assertEqual(dict(os.environ), before)

    def test_repr_never_contains_tokens(self):
        self.write(f'TELEGRAM_BOT_TOKEN={TOKEN}\nTRADEE_WEB_OPERATOR_TOKEN=operator-secret\n')
        text = repr(load_environment(self.path, {}))
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("operator-secret", text)

    def test_unreadable_and_invalid_encoding_errors_are_redacted(self):
        self.write("configured")
        with patch("pathlib.Path.open", side_effect=PermissionError(TOKEN)):
            with self.assertRaisesRegex(ValidationError, '^Cannot read Tradee .env configuration$'):
                load_environment(self.path, {})
        self.path.write_bytes(b'\xff' + TOKEN.encode())
        with self.assertRaisesRegex(ValidationError, '^Cannot read Tradee .env configuration$'):
            load_environment(self.path, {})


class TelegramEnvironmentCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / ".env"
        self.path.write_text(f'TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID={CHAT}\n')
        for context in (patch("tradee.environment.ROOT_ENV", self.path), patch.dict(os.environ, {}, clear=True)):
            context.start()
            self.addCleanup(context.stop)

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["signals", *args])
        text = out.getvalue() + err.getvalue()
        self.assertNotIn(TOKEN, text)
        return code, json.loads(text)

    def test_dotenv_destination_defaults_send_once_through_mock_only(self):
        with patch("tradee.c14.cli.TelegramTransport") as transport:
            transport.return_value.send.return_value = DeliveryResult("sent", "telegram_accepted", 1)
            code, doc = self.call("telegram-test", "--test-id", "env_test", "--send-paper")
            transport.assert_called_once_with(TOKEN, 123456789)
            transport.return_value.send.assert_called_once()
            self.assertEqual(transport.return_value.send.call_args.args[0], CHAT)
        self.assertEqual(code, 0)
        self.assertTrue(doc["ready"])
        self.assertEqual(doc["bot_id"], 123456789)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.path])

    def test_explicit_destination_beats_env_and_exports_beat_file(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": OTHER}), patch("tradee.c14.cli.TelegramTransport") as transport:
            transport.return_value.send.return_value = DeliveryResult("sent", "telegram_accepted", 1)
            self.assertEqual(self.call("telegram-test", "--bot-id", "987654321", "--chat-id", "-42", "--test-id", "override", "--send-paper")[0], 0)
            transport.assert_called_once_with(OTHER, 987654321)
            self.assertEqual(transport.return_value.send.call_args.args[0], -42)

    def test_mismatched_explicit_bot_cannot_build_or_call_network(self):
        with patch("tradee.c14.telegram.request.build_opener") as opener:
            code, doc = self.call("telegram-test", "--bot-id", "987654321", "--test-id", "mismatch", "--send-paper")
            opener.assert_not_called()
        self.assertEqual(code, 1)
        self.assertIn("credential", doc["error"])

    def test_missing_or_invalid_defaults_stop_before_transport(self):
        for content in ("", f'TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=invalid\n',
                        f'TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=0\n'):
            self.path.write_text(content)
            with patch("tradee.c14.cli.TelegramTransport") as transport:
                self.assertEqual(self.call("telegram-test", "--test-id", "invalid", "--send-paper")[0], 1)
                transport.assert_not_called()

    def test_credentials_do_not_remove_send_opt_in_or_change_shadow_default(self):
        with patch("tradee.c14.cli.TelegramTransport") as transport:
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                main(["signals", "telegram-test", "--test-id", "no_consent"])
            code, doc = self.call("explain")
            transport.assert_not_called()
        self.assertEqual(code, 0)
        self.assertEqual(doc["runtime"]["mode"], "shadow")
        self.assertIsNone(doc["runtime"]["chat_id"])
