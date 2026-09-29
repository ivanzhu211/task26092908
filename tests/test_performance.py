"""Non-functional: 500 rules x 1000 records within 5 seconds."""

import time

from mapping_engine import Rule, RuleSet, transform_batch


def test_full_load_under_five_seconds():
    rules = [
        Rule(target="employee_id", source_path="id", transform="id_string"),
        Rule(target="first_name", source_path="fn"),
        Rule(target="last_name", source_path="ln"),
        Rule(target="email", source_path="em"),
        Rule(
            target="status",
            source_path="st",
            transform="status",
            has_default=True,
            default="active",
        ),
        Rule(target="start_date", source_path="hired", transform="date"),
        Rule(target="is_contractor", source_path="ct", transform="bool"),
        Rule(target="weekly_hours", source_path="hrs", transform="int"),
    ]
    # pad to the 500-rule maximum with intermediate pass-through fields
    rules += [Rule(target=f"extra_{i}", source_path=f"x{i}") for i in range(492)]
    assert len(rules) == 500
    rs = RuleSet("perf", 1, tuple(rules))

    record = {
        "id": "0076",
        "fn": "Ada",
        "ln": "L",
        "em": "a@x.co",
        "st": "active",
        "hired": "2024-02-29",
        "ct": "no",
        "hrs": "40",
        **{f"x{i}": i for i in range(492)},
    }
    records = [dict(record, id=f"{i:05d}") for i in range(1000)]

    start = time.perf_counter()
    batch = transform_batch(rs, records)
    elapsed = time.perf_counter() - start

    assert batch.succeeded == 1000
    assert elapsed < 5.0, f"batch took {elapsed:.2f}s"
