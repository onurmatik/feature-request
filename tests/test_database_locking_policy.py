import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "migrations", "tests"}


def _production_python_files():
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.name == "tests.py" or path.name.startswith("test_"):
            continue
        yield path


def _declares_lock_targets(call):
    keyword = next((item for item in call.keywords if item.arg == "of"), None)
    if keyword is None:
        return False
    try:
        targets = ast.literal_eval(keyword.value)
    except (ValueError, TypeError):
        return False
    return (
        isinstance(targets, (tuple, list))
        and bool(targets)
        and all(isinstance(target, str) and target for target in targets)
    )


def _lock_target_violations(tree):
    violations = set()
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != "select_for_update"
        ):
            continue
        if not _declares_lock_targets(node):
            violations.add(node.lineno)
    return violations


class DatabaseLockingPolicyTest(unittest.TestCase):
    def test_detector_rejects_lock_without_explicit_targets(self):
        tree = ast.parse(
            'Issue.objects.select_for_update().select_related("project").get(pk=1)'
        )

        self.assertEqual(_lock_target_violations(tree), {1})

    def test_detector_accepts_explicit_lock_targets(self):
        tree = ast.parse(
            'Issue.objects.select_for_update(of=("self",)).select_related("project").get(pk=1)'
        )

        self.assertEqual(_lock_target_violations(tree), set())

    def test_detector_rejects_empty_lock_targets(self):
        tree = ast.parse("Issue.objects.select_for_update(of=()).get(pk=1)")

        self.assertEqual(_lock_target_violations(tree), {1})

    def test_row_locks_declare_their_targets(self):
        violations = []
        for path in _production_python_files():
            tree = ast.parse(path.read_text(), filename=str(path))
            for line in sorted(_lock_target_violations(tree)):
                violations.append(f"{path.relative_to(ROOT)}:{line}")

        self.assertEqual(
            violations,
            [],
            "Every select_for_update() call must declare non-empty literal "
            "of= lock targets:\n" + "\n".join(violations),
        )
