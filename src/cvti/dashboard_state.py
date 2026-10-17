"""Local recovery snapshots for dashboard sessions, separate from research records."""
import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path

from cvti.config import get_settings


STATE_KEYS = {
    "workspace_nav", "active_project", "scoring_model", "profile_smiles",
    "comparison_smiles", "molecule_profile", "profile_prediction", "comparison_result",
}
MOLECULE_KEYS = STATE_KEYS - {"workspace_nav", "active_project", "scoring_model"}


def workspace_token(value: str | None) -> str:
    """Only opaque identifiers may become filenames; never accept a supplied path."""
    return value if value and re.fullmatch(r"[0-9a-f]{32}", value) else secrets.token_hex(16)


class WorkspaceStore:
    def __init__(self, api_url: str):
        namespace = hashlib.sha256(api_url.encode()).hexdigest()[:16]
        self.directory = Path(os.getenv("WORKSPACE_STATE_DIR") or get_settings().workspace_state_dir) / namespace

    def load(self, token: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValueError("Invalid workspace identifier")
        try:
            payload = json.loads((self.directory / f"{token}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        state = payload.get("state") if isinstance(payload, dict) else None
        if (not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(state, dict)
                or payload.get("sha256") != self._checksum(state)):
            raise ValueError("Invalid workspace snapshot")
        return {key: value for key, value in state.items() if key in STATE_KEYS}

    @staticmethod
    def _checksum(state: dict) -> str:
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def save(self, token: str, session) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValueError("Invalid workspace identifier")
        state = {key: session[key] for key in STATE_KEYS if key in session}
        payload = json.dumps({"version": 1, "state": state, "sha256": self._checksum(state)})
        self.directory.mkdir(parents=True, exist_ok=True)
        # Replace atomically so a stopped process cannot leave a partial snapshot.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
            temporary.replace(self.directory / f"{token}.json")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
