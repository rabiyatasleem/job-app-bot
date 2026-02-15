"""User profile management — stores candidate info used across the pipeline."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class UserProfile:
    """All candidate information needed for applications."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience_years: int = 0
    education: list[dict] = field(default_factory=list)
    work_history: list[dict] = field(default_factory=list)
    base_resume_path: str = ""


class ProfileManager:
    """Load, save, and update user profiles stored as JSON files.

    Profiles live in the ``config/`` directory by default.

    Usage:
        pm = ProfileManager()
        profile = pm.load("default")
        profile.skills.append("Python")
        pm.save(profile, "default")
    """

    def __init__(self, profiles_dir: str = "config/profiles") -> None:
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def load(self, name: str = "default") -> UserProfile:
        """Load a profile from disk.

        Args:
            name: Profile name (filename without extension).

        Returns:
            UserProfile populated from the JSON file, or a blank profile
            if the file doesn't exist.
        """
        path = self._dir / f"{name}.json"
        if not path.exists():
            return UserProfile()
        data = json.loads(path.read_text(encoding="utf-8"))
        return UserProfile(**data)

    def save(self, profile: UserProfile, name: str = "default") -> Path:
        """Persist a profile to disk.

        Args:
            profile: The UserProfile to save.
            name: Profile name (filename without extension).

        Returns:
            Path to the saved JSON file.
        """
        path = self._dir / f"{name}.json"
        path.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
        return path

    def list_profiles(self) -> list[str]:
        """Return names of all saved profiles."""
        return [p.stem for p in self._dir.glob("*.json")]

    def delete(self, name: str) -> None:
        """Delete a profile by name.

        Args:
            name: Profile name to delete.
        """
        path = self._dir / f"{name}.json"
        if path.exists():
            path.unlink()
