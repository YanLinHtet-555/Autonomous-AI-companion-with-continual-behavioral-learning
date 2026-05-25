import json
import os
from datetime import datetime


DEFAULT_CONSENT = {
    "monitor_apps": True,
    "monitor_code": True,
    "monitor_tasks": True,
    "monitor_time": True,
    "monitor_input": False,   # always off unless explicitly turned on
    "excluded_apps": ["1Password", "KeePass", "Bitwarden", "banking"],
    "consent_given_at": None,
    "last_updated": None,
}


class ConsentManager:
    """
    Manages what the AI is allowed to monitor.
    User must explicitly grant consent on first run.
    All monitoring can be paused or reconfigured at any time.
    """

    def __init__(self, consent_path):
        self.consent_path = consent_path
        self._consent = None
        os.makedirs(os.path.dirname(consent_path), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.consent_path):
            with open(self.consent_path) as f:
                self._consent = json.load(f)
        else:
            self._consent = dict(DEFAULT_CONSENT)

    def _save(self):
        self._consent["last_updated"] = datetime.now().isoformat()
        with open(self.consent_path, "w") as f:
            json.dump(self._consent, f, indent=2)

    def has_consented(self):
        return self._consent.get("consent_given_at") is not None

    def grant_consent(self, settings: dict = None):
        if settings:
            self._consent.update(settings)
        self._consent["consent_given_at"] = datetime.now().isoformat()
        self._save()
        print("[Privacy] Consent recorded.")

    def revoke_all(self):
        self._consent = dict(DEFAULT_CONSENT)
        self._save()
        print("[Privacy] All monitoring disabled. Data collection paused.")

    def get(self, key, default=None):
        return self._consent.get(key, default)

    def set(self, key, value):
        self._consent[key] = value
        self._save()
        print(f"[Privacy] {key} set to {value}")

    def add_excluded_app(self, app_name):
        excluded = self._consent.get("excluded_apps", [])
        if app_name not in excluded:
            excluded.append(app_name)
            self._consent["excluded_apps"] = excluded
            self._save()
            print(f"[Privacy] '{app_name}' added to exclusion list")

    def show(self):
        print("\n--- Privacy Settings ---")
        for k, v in self._consent.items():
            print(f"  {k}: {v}")
        print("------------------------\n")

    def as_dict(self):
        return dict(self._consent)
