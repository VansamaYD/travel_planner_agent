from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "travel_agent"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_domain_does_not_import_frameworks() -> None:
    banned = ("fastapi", "sqlalchemy", "httpx", "pydantic_settings")
    violations: list[str] = []
    for path in SOURCE_ROOT.glob("modules/*/domain/**/*.py"):
        for module in imported_modules(path):
            if module.startswith(banned):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} -> {module}")
    assert violations == []


def test_api_does_not_import_sqlalchemy_or_provider_sdks() -> None:
    banned = ("sqlalchemy", "httpx")
    violations: list[str] = []
    for path in (SOURCE_ROOT / "api").rglob("*.py"):
        for module in imported_modules(path):
            if module.startswith(banned):
                violations.append(f"{path.relative_to(SOURCE_ROOT)} -> {module}")
    assert violations == []


def test_modules_do_not_import_other_modules_infrastructure() -> None:
    violations: list[str] = []
    for path in (SOURCE_ROOT / "modules").rglob("*.py"):
        owner = path.relative_to(SOURCE_ROOT / "modules").parts[0]
        marker = "travel_agent.modules."
        for module in imported_modules(path):
            if not module.startswith(marker) or ".infrastructure" not in module:
                continue
            target = module.removeprefix(marker).split(".", 1)[0]
            if target != owner:
                violations.append(f"{path.relative_to(SOURCE_ROOT)} -> {module}")
    assert violations == []
