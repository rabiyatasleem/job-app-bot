"""Tests for UserProfile dataclass and ProfileManager."""

import json
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")

import pytest

from src.profiles.manager import ProfileManager, UserProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def profiles_dir(tmp_path):
    """Provide a temporary directory for profile storage."""
    return tmp_path / "profiles"


@pytest.fixture()
def pm(profiles_dir):
    """ProfileManager pointing at a temp directory."""
    return ProfileManager(profiles_dir=str(profiles_dir))


SAMPLE_PROFILE = UserProfile(
    full_name="Jane Doe",
    email="jane@example.com",
    phone="+1-555-0100",
    location="New York, NY",
    linkedin_url="https://linkedin.com/in/janedoe",
    github_url="https://github.com/janedoe",
    portfolio_url="https://janedoe.dev",
    summary="Experienced backend engineer.",
    skills=["Python", "SQL", "AWS"],
    experience_years=5,
    education=[{"school": "MIT", "degree": "BS CS", "year": 2019}],
    work_history=[{"company": "Acme", "role": "Engineer", "years": 3}],
    base_resume_path="/home/jane/resume.md",
)


# ===================================================================
# UserProfile dataclass
# ===================================================================

class TestUserProfile:

    def test_all_defaults_empty(self):
        p = UserProfile()
        assert p.full_name == ""
        assert p.email == ""
        assert p.phone == ""
        assert p.location == ""
        assert p.linkedin_url == ""
        assert p.github_url == ""
        assert p.portfolio_url == ""
        assert p.summary == ""
        assert p.skills == []
        assert p.experience_years == 0
        assert p.education == []
        assert p.work_history == []
        assert p.base_resume_path == ""

    def test_construct_with_all_fields(self):
        p = SAMPLE_PROFILE
        assert p.full_name == "Jane Doe"
        assert p.skills == ["Python", "SQL", "AWS"]
        assert p.experience_years == 5
        assert len(p.education) == 1
        assert len(p.work_history) == 1

    def test_skills_list_is_independent(self):
        """Each instance should get its own list, not a shared ref."""
        p1 = UserProfile()
        p2 = UserProfile()
        p1.skills.append("Go")
        assert "Go" not in p2.skills


# ===================================================================
# ProfileManager — __init__
# ===================================================================

class TestInit:

    def test_creates_directory(self, profiles_dir):
        assert not profiles_dir.exists()
        ProfileManager(profiles_dir=str(profiles_dir))
        assert profiles_dir.exists()

    def test_existing_directory_ok(self, profiles_dir):
        profiles_dir.mkdir(parents=True)
        pm = ProfileManager(profiles_dir=str(profiles_dir))
        assert pm._dir == profiles_dir

    def test_nested_directory_created(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        ProfileManager(profiles_dir=str(deep))
        assert deep.exists()


# ===================================================================
# ProfileManager — save
# ===================================================================

class TestSave:

    def test_save_creates_json_file(self, pm, profiles_dir):
        path = pm.save(SAMPLE_PROFILE, "jane")

        assert path.exists()
        assert path.name == "jane.json"
        assert path.parent == profiles_dir

    def test_save_returns_path(self, pm):
        path = pm.save(UserProfile(), "empty")
        assert str(path).endswith("empty.json")

    def test_saved_json_is_valid(self, pm):
        pm.save(SAMPLE_PROFILE, "jane")
        raw = (pm._dir / "jane.json").read_text(encoding="utf-8")
        data = json.loads(raw)

        assert data["full_name"] == "Jane Doe"
        assert data["skills"] == ["Python", "SQL", "AWS"]
        assert data["experience_years"] == 5

    def test_save_overwrites_existing(self, pm):
        pm.save(UserProfile(full_name="V1"), "test")
        pm.save(UserProfile(full_name="V2"), "test")

        data = json.loads((pm._dir / "test.json").read_text(encoding="utf-8"))
        assert data["full_name"] == "V2"

    def test_save_default_name(self, pm):
        path = pm.save(UserProfile(full_name="Default"))
        assert path.name == "default.json"

    def test_saved_json_is_indented(self, pm):
        pm.save(SAMPLE_PROFILE, "pretty")
        raw = (pm._dir / "pretty.json").read_text(encoding="utf-8")
        # Indented JSON has newlines
        assert "\n" in raw


# ===================================================================
# ProfileManager — load
# ===================================================================

class TestLoad:

    def test_load_returns_blank_when_missing(self, pm):
        profile = pm.load("nonexistent")

        assert profile.full_name == ""
        assert profile.skills == []

    def test_load_roundtrips_all_fields(self, pm):
        pm.save(SAMPLE_PROFILE, "jane")
        loaded = pm.load("jane")

        assert loaded.full_name == "Jane Doe"
        assert loaded.email == "jane@example.com"
        assert loaded.phone == "+1-555-0100"
        assert loaded.location == "New York, NY"
        assert loaded.linkedin_url == "https://linkedin.com/in/janedoe"
        assert loaded.github_url == "https://github.com/janedoe"
        assert loaded.portfolio_url == "https://janedoe.dev"
        assert loaded.summary == "Experienced backend engineer."
        assert loaded.skills == ["Python", "SQL", "AWS"]
        assert loaded.experience_years == 5
        assert loaded.education == [{"school": "MIT", "degree": "BS CS", "year": 2019}]
        assert loaded.work_history == [{"company": "Acme", "role": "Engineer", "years": 3}]
        assert loaded.base_resume_path == "/home/jane/resume.md"

    def test_load_default_name(self, pm):
        pm.save(UserProfile(full_name="Default User"))
        loaded = pm.load()
        assert loaded.full_name == "Default User"

    def test_load_after_overwrite(self, pm):
        pm.save(UserProfile(full_name="Old"), "update")
        pm.save(UserProfile(full_name="New"), "update")

        loaded = pm.load("update")
        assert loaded.full_name == "New"


# ===================================================================
# ProfileManager — list_profiles
# ===================================================================

class TestListProfiles:

    def test_empty_directory(self, pm):
        assert pm.list_profiles() == []

    def test_lists_saved_profiles(self, pm):
        pm.save(UserProfile(), "alice")
        pm.save(UserProfile(), "bob")

        names = sorted(pm.list_profiles())
        assert names == ["alice", "bob"]

    def test_excludes_non_json_files(self, pm):
        pm.save(UserProfile(), "real")
        (pm._dir / "notes.txt").write_text("not a profile")

        assert pm.list_profiles() == ["real"]

    def test_returns_stems_not_full_paths(self, pm):
        pm.save(UserProfile(), "myprofile")

        names = pm.list_profiles()
        assert "myprofile" in names
        assert not any(".json" in n for n in names)


# ===================================================================
# ProfileManager — delete
# ===================================================================

class TestDelete:

    def test_delete_removes_file(self, pm):
        pm.save(UserProfile(), "temp")
        assert (pm._dir / "temp.json").exists()

        pm.delete("temp")
        assert not (pm._dir / "temp.json").exists()

    def test_delete_nonexistent_does_not_raise(self, pm):
        pm.delete("ghost")  # should be a noop

    def test_delete_leaves_other_profiles(self, pm):
        pm.save(UserProfile(), "keep")
        pm.save(UserProfile(), "remove")

        pm.delete("remove")

        assert pm.list_profiles() == ["keep"]

    def test_load_after_delete_returns_blank(self, pm):
        pm.save(UserProfile(full_name="Gone"), "deleted")
        pm.delete("deleted")

        loaded = pm.load("deleted")
        assert loaded.full_name == ""
