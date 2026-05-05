"""Architecture tests -- enforce type safety invariants via AST.

These tests parse the codebase and fail loudly if someone reintroduces
weak types (Any, bare dict, object params, etc.). They run in CI via
the pre-commit hook and prevent type safety regressions.

Performance: all source files are read and parsed ONCE at module load.
Every test reads from the cache -- no redundant I/O or parsing.
"""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path
from typing import ClassVar

# Production source directory
SRC_DIR = Path(__file__).parent.parent / "src" / "decaf"

# Files excluded from type enforcement (kept for future use, not actively maintained)
_EXCLUDED_FILES = {
    "schwab_auth.py",  # Future Schwab API OAuth -- aiohttp types resolve at runtime
    "schwab_client.py",  # Future Schwab API client -- same
}


# ---------------------------------------------------------------------------
# Shared parsed source -- read and AST-parsed exactly once at module load.
# ---------------------------------------------------------------------------


class _ParsedSource:
    """All .py source in SRC_DIR -- read and AST-parsed exactly once."""

    def __init__(self) -> None:
        self.content: dict[str, str] = {}  # relative_path -> source text
        self.trees: dict[str, ast.Module] = {}  # relative_path -> parsed AST

        for path in sorted(SRC_DIR.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = str(path.relative_to(SRC_DIR))
            text = path.read_text()
            self.content[rel] = text
            with contextlib.suppress(SyntaxError):
                self.trees[rel] = ast.parse(text, filename=rel)


# Singleton -- populated once at module import, reused by every test.
_parsed_src = _ParsedSource()


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _file_imports_name(tree: ast.Module, name: str) -> bool:
    """Check if an AST imports a specific name from any module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name or (alias.asname and alias.asname == name):
                    return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == name or (alias.asname and alias.asname == name):
                    return True
    return False


def _find_annotations(tree: ast.Module) -> list[tuple[int, str]]:
    """Find all type annotation strings in an AST.

    Returns (lineno, annotation_text) for every annotation node.
    Walks function args, return types, variable annotations, and
    subscript annotations.
    """
    results: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # Function arguments and return type
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                if arg.annotation:
                    results.append((arg.annotation.lineno, ast.dump(arg.annotation)))
            if node.returns:
                results.append((node.returns.lineno, ast.dump(node.returns)))

        # Variable annotations: x: SomeType = ...
        if isinstance(node, ast.AnnAssign) and node.annotation:
            results.append((node.annotation.lineno, ast.dump(node.annotation)))

    return results


# ---------------------------------------------------------------------------
# Type safety tests
# ---------------------------------------------------------------------------


class TestNoAny:
    """typing.Any must never appear in production source."""

    def test_no_any_import(self) -> None:
        """No file may import Any from typing."""
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            if _file_imports_name(tree, "Any"):
                violations.append(f"{filename}: imports Any")

        assert not violations, (
            "typing.Any imported -- use TypedDict, Protocol, or concrete types:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_no_any_in_annotations(self) -> None:
        """No type annotation may reference 'Any'."""
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for lineno, ann_dump in _find_annotations(tree):
                # ast.dump of Name(id='Any') or Attribute with 'Any'
                if "'Any'" in ann_dump:
                    violations.append(f"{filename}:{lineno}")

        assert not violations, "Any used in type annotation -- use concrete types:\n" + "\n".join(
            f"  {v}" for v in violations
        )


class TestNoBareDict:
    """Bare 'dict' without type parameters must not appear in annotations."""

    def test_no_bare_dict_annotation(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for lineno, ann_dump in _find_annotations(tree):
                # ast.dump of a bare Name(id='dict') -- NOT Subscript(value=Name(id='dict'))
                # We check for Name(id='dict') that is NOT inside a Subscript
                if "Name(id='dict')" in ann_dump and "Subscript" not in ann_dump:
                    violations.append(f"{filename}:{lineno}")

        assert not violations, (
            "Bare 'dict' in annotation -- use dict[K, V] or TypedDict:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_no_bare_list_annotation(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for lineno, ann_dump in _find_annotations(tree):
                if "Name(id='list')" in ann_dump and "Subscript" not in ann_dump:
                    violations.append(f"{filename}:{lineno}")

        assert not violations, "Bare 'list' in annotation -- use list[T]:\n" + "\n".join(
            f"  {v}" for v in violations
        )

    def test_no_bare_tuple_annotation(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for lineno, ann_dump in _find_annotations(tree):
                if "Name(id='tuple')" in ann_dump and "Subscript" not in ann_dump:
                    violations.append(f"{filename}:{lineno}")

        assert not violations, "Bare 'tuple' in annotation -- use tuple[T, ...]:\n" + "\n".join(
            f"  {v}" for v in violations
        )

    def test_no_bare_set_annotation(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for lineno, ann_dump in _find_annotations(tree):
                if "Name(id='set')" in ann_dump and "Subscript" not in ann_dump:
                    violations.append(f"{filename}:{lineno}")

        assert not violations, "Bare 'set' in annotation -- use set[T]:\n" + "\n".join(
            f"  {v}" for v in violations
        )


class TestNoObjectParams:
    """Function parameters typed as 'object' are too loose.

    Exception: __exit__ / __aexit__ use *exc: object (standard protocol),
    and json.JSONEncoder.default() overrides use object (required signature).
    """

    def test_no_object_param_type(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                # Skip dunder methods (__exit__, __aexit__, etc.)
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue

                for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                    if arg.arg == "self":
                        continue
                    if arg.annotation and ast.dump(arg.annotation) == "Name(id='object')":
                        violations.append(
                            f"{filename}:{arg.annotation.lineno}: {node.name}({arg.arg}: object)"
                        )

        assert not violations, "Parameter typed as 'object' -- use a concrete type:\n" + "\n".join(
            f"  {v}" for v in violations
        )


class TestDecimalSafety:
    """sum() over Decimal fields must use Decimal(0) start to avoid int|Decimal."""

    def test_sum_over_decimal_has_start(self) -> None:
        """Every sum() call in production code should have a start value
        when summing Decimal attributes (prevents int|Decimal union type).
        """
        violations = []
        # Known Decimal attribute patterns from our models
        decimal_attrs = {
            "ivafe_due",
            "gain_loss_eur",
            "gross_amount_eur",
            "wht_amount_eur",
            "final_value_eur",
            "initial_value_eur",
            "proceeds_eur",
            "cost_basis_eur",
            "quantity",
            "amount",
            "remaining",
        }

        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name) and node.func.id == "sum"):
                    continue

                # Check if the sum references a known Decimal attribute
                sum_source = ast.dump(node)
                references_decimal = any(attr in sum_source for attr in decimal_attrs)
                if not references_decimal:
                    continue

                # Must have 2 args: sum(generator, start_value)
                if len(node.args) < 2:
                    violations.append(f"{filename}:{node.lineno}: sum() without Decimal(0) start")

        assert not violations, (
            "sum() over Decimal fields without start value -- "
            "use sum(..., Decimal(0)) to avoid int|Decimal union:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


def _is_inside_logger_call(node: ast.AST, tree: ast.Module) -> bool:
    """Check if a node is an argument inside a logger.xxx() call."""
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Call):
            continue
        # logger.info(...), logger.warning(...), etc.
        if not (
            isinstance(parent.func, ast.Attribute)
            and parent.func.attr in ("debug", "info", "warning", "error", "critical")
        ):
            continue
        # Check if our node is among the call's args
        for arg in parent.args:
            if arg is node:
                return True
            # Also check nested: float(x) inside the arg expression
            for child in ast.walk(arg):
                if child is node:
                    return True
    return False


def _is_inside_function(node: ast.AST, tree: ast.Module, func_name: str) -> bool:
    """Check if a node is inside a specific function definition."""
    for parent in ast.walk(tree):
        if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if parent.name != func_name:
            continue
        for child in ast.walk(parent):
            if child is node:
                return True
    return False


class TestNoFloat:
    """float() must never be called in computation code.

    Allowed per-call (not per-file):
    - Inside logger.info/warning/debug/error calls (logging formatting)
    - Output serialization files (openpyxl, fpdf2, json encoder)
    - _fetch_year_end_prices (yfinance returns float)
    """

    # ONLY files that must pass floats to external serialization APIs
    _FLOAT_ALLOWED_FILES: ClassVar[set[str]] = {
        "output_xls.py",  # openpyxl cell values must be float
        "output_pdf.py",  # fpdf2 values must be float
        "output_json.py",  # json.JSONEncoder.default() can't serialize Decimal
    }

    def test_no_float_on_decimal_in_computation(self) -> None:
        """float() only allowed in logging calls and output serialization."""
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            if filename in self._FLOAT_ALLOWED_FILES:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if not (isinstance(node.func, ast.Name) and node.func.id == "float"):
                    continue

                # Allow: float() inside logger.xxx() calls
                if _is_inside_logger_call(node, tree):
                    continue

                # Allow: float() in fetch_year_end_prices (yfinance returns numpy float)
                if _is_inside_function(node, tree, "fetch_year_end_prices"):
                    continue

                violations.append(f"{filename}:{node.lineno}: float() call")

        assert not violations, (
            "float() called outside allowed context -- "
            "use Decimal throughout, float() only in logging/output:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


class TestAllFunctionsTyped:
    """Every function must have a return type annotation."""

    def test_all_functions_have_return_type(self) -> None:
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            if filename == "__init__.py":
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                # Skip property getters (return type inferred)
                decorators = [ast.dump(d) for d in node.decorator_list]
                if any("property" in d for d in decorators):
                    continue
                if node.returns is None:
                    violations.append(f"{filename}:{node.lineno}: {node.name}()")

        assert not violations, "Function missing return type annotation:\n" + "\n".join(
            f"  {v}" for v in violations
        )

    def test_all_params_have_type(self) -> None:
        """Every function parameter (except self/cls) must be typed."""
        violations = []
        for filename, tree in _parsed_src.trees.items():
            if filename in _EXCLUDED_FILES:
                continue
            if filename == "__init__.py":
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for arg in node.args.args:
                    if arg.arg in ("self", "cls"):
                        continue
                    if arg.annotation is None:
                        violations.append(
                            f"{filename}:{node.lineno}: {node.name}({arg.arg}) missing type"
                        )

        assert not violations, "Function parameter missing type annotation:\n" + "\n".join(
            f"  {v}" for v in violations
        )
