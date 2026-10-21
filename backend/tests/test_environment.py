import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.tradee_web.config import load_settings


class WebEnvironmentTests(unittest.TestCase):
    def test_api_and_worker_shared_settings_read_root_dotenv(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".env"
            path.write_text('TRADEE_WEB_OPERATOR_TOKEN="private-operator-token"\n')
            with patch("tradee.environment.ROOT_ENV", path), patch.dict(os.environ, {}, clear=True):
                settings = load_settings()
                self.assertEqual(settings.operator_token, "private-operator-token")
                self.assertNotIn("private-operator-token", repr(settings))
                self.assertEqual(load_settings(operator_token="").operator_token, "")
                with patch.dict(os.environ, {"TRADEE_WEB_OPERATOR_TOKEN": "exported"}):
                    self.assertEqual(load_settings().operator_token, "exported")
                with patch.dict(os.environ, {"TRADEE_WEB_OPERATOR_TOKEN": ""}):
                    self.assertEqual(load_settings().operator_token, "")
