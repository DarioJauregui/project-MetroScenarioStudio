from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from metro_demand_models.configuration import load_settings


DEPENDENCIES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "pyarrow": "pyarrow",
    "openpyxl": "openpyxl",
    "scikit-learn": "scikit-learn",
    "matplotlib": "matplotlib",
    "shap": "shap",
    "mlflow": "mlflow",
    "pytest": "pytest",
}


def collect_dependency_versions() -> tuple[dict[str, str], list[str]]:
    installed_versions: dict[str, str] = {}
    missing_dependencies: list[str] = []

    for dependency_name in DEPENDENCIES.values():
        try:
            installed_versions[dependency_name] = version(dependency_name)
        except PackageNotFoundError:
            missing_dependencies.append(dependency_name)

    return installed_versions, missing_dependencies


def build_environment_report(project_root: Path | None = None) -> dict[str, Any]:
    settings = load_settings(project_root)
    dependency_versions, missing_dependencies = collect_dependency_versions()
    python_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    expected_python = str(settings["project"]["python_version"])

    return {
        "project_name": settings["project"]["name"],
        "project_root": settings["runtime"]["project_root"],
        "config_files": settings["runtime"]["loaded_config_files"],
        "python": {
            "current": sys.version.split()[0],
            "major_minor": python_major_minor,
            "expected": expected_python,
            "matches_project": python_major_minor == expected_python,
        },
        "dependencies": dependency_versions,
        "missing_dependencies": missing_dependencies,
    }


def validate_environment(project_root: Path | None = None) -> list[str]:
    report = build_environment_report(project_root)
    issues: list[str] = []

    if not report["python"]["matches_project"]:
        issues.append(f"Python interpreter does not match the project requirement ({report['python']['expected']}).")

    if report["missing_dependencies"]:
        missing_list = ", ".join(report["missing_dependencies"])
        issues.append(f"Missing project dependencies: {missing_list}.")

    return issues


def format_environment_report(report: dict[str, Any]) -> str:
    dependency_lines = [
        f"- {dependency_name}: {dependency_version}"
        for dependency_name, dependency_version in sorted(report["dependencies"].items())
    ]
    dependencies_block = "\n".join(dependency_lines) if dependency_lines else "- None"

    missing_lines = [f"- {dependency_name}" for dependency_name in report["missing_dependencies"]]
    missing_block = "\n".join(missing_lines) if missing_lines else "- None"

    lines = [
        "Environment report",
        f"Project: {report['project_name']}",
        f"Project root: {report['project_root']}",
        f"Python current: {report['python']['current']}",
        f"Python expected: {report['python']['expected']}",
        f"Python matches project: {report['python']['matches_project']}",
        "Loaded config files:",
        *[f"- {path}" for path in report["config_files"]],
        "Installed dependency versions:",
        dependencies_block,
        "Missing dependencies:",
        missing_block,
    ]
    return "\n".join(lines)


def main(project_root: Path | None = None) -> int:
    report = build_environment_report(project_root)
    issues = validate_environment(project_root)
    print(format_environment_report(report))

    if issues:
        print("\nValidation issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("\nEnvironment validation passed.")
    return 0
