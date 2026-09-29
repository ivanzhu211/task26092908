"""Rule set validation: rejects invalid rule sets with all issues listed."""

from __future__ import annotations

from .convert import TRANSFORMS, convert
from .models import FIELD_TYPES, MAX_RULES, Rule

REF_PREFIX = "$"  # source_path "$name" references another rule's output


def _ref_name(source_path: str | None) -> str | None:
    if source_path and source_path.startswith(REF_PREFIX):
        return source_path[len(REF_PREFIX):]
    return None


def _check_value_type(value: object, type_name: str, where: str, issues: list[str]) -> None:
    try:
        convert(value, type_name)
    except ValueError as exc:
        issues.append(f"{where}: value {value!r} does not fit type {type_name}: {exc}")


def validate_rules(rules: list[Rule]) -> list[str]:
    """Return a list of validation issues (empty means valid)."""
    issues: list[str] = []

    if len(rules) > MAX_RULES:
        issues.append(f"rule set has {len(rules)} rules, max is {MAX_RULES}")

    seen: dict[str, int] = {}
    for idx, rule in enumerate(rules):
        where = f"rule[{idx}] (target {rule.target!r})"
        if rule.target in seen:
            issues.append(
                f"{where}: target defined more than once "
                f"(first at rule[{seen[rule.target]}])"
            )
        else:
            seen[rule.target] = idx
        if rule.transform is not None and rule.transform not in TRANSFORMS:
            issues.append(f"{where}: unknown transform {rule.transform!r}")

    defined = set(seen)

    # references to undefined fields
    deps: dict[int, set[int]] = {idx: set() for idx in range(len(rules))}
    for idx, rule in enumerate(rules):
        where = f"rule[{idx}] (target {rule.target!r})"
        ref = _ref_name(rule.source_path)
        if ref is not None:
            if ref not in defined:
                issues.append(f"{where}: references undefined field {ref!r}")
            elif ref != rule.target:
                deps[idx].add(seen[ref])
            else:
                deps[idx].add(idx)

    # type-check defaults and condition results against the target type
    for idx, rule in enumerate(rules):
        where = f"rule[{idx}] (target {rule.target!r})"
        type_name = FIELD_TYPES.get(rule.target, rule.transform)
        if type_name is None:
            continue
        if rule.has_default:
            _check_value_type(rule.default, type_name, f"{where} default", issues)
        for cidx, cond in enumerate(rule.conditions):
            _check_value_type(
                cond.value, type_name, f"{where} condition[{cidx}]", issues
            )

    issues.extend(_find_cycles(rules, deps))
    return issues


def _find_cycles(rules: list[Rule], deps: dict[int, set[int]]) -> list[str]:
    issues: list[str] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {idx: WHITE for idx in deps}
    reported: set[frozenset[int]] = set()

    def visit(idx: int, stack: list[int]) -> None:
        color[idx] = GRAY
        stack.append(idx)
        for dep in deps[idx]:
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    names = " -> ".join(repr(rules[i].target) for i in cycle)
                    issues.append(f"circular reference detected: {names}")
            elif color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[idx] = BLACK

    for idx in deps:
        if color[idx] == WHITE:
            visit(idx, [])
    return issues
