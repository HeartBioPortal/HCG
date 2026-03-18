from __future__ import annotations

from pathlib import Path

from hcg.paths import detect_project_root


def test_detect_project_root_prefers_env_override(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    detected = detect_project_root(
        module_file=repo_root / "src" / "hcg" / "paths.py",
        cwd=tmp_path,
        env_root=str(repo_root),
    )

    assert detected == repo_root.resolve()


def test_detect_project_root_finds_repo_from_cwd_when_module_file_is_in_site_packages(tmp_path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src" / "hcg").mkdir(parents=True)
    (repo_root / "data").mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='hcg'\n", encoding="utf-8")

    site_packages_file = (
        repo_root / ".venv" / "lib" / "python3.12" / "site-packages" / "hcg" / "paths.py"
    )

    detected = detect_project_root(
        module_file=site_packages_file,
        cwd=repo_root,
        env_root=None,
    )

    assert detected == repo_root.resolve()


def test_detect_project_root_falls_back_to_module_parent_when_no_repo_markers_exist(tmp_path) -> None:
    module_file = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages" / "hcg" / "paths.py"
    cwd = tmp_path / "elsewhere"

    detected = detect_project_root(
        module_file=module_file,
        cwd=cwd,
        env_root=None,
    )

    assert detected == cwd.resolve()
