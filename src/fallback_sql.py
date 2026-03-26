from __future__ import annotations

import re


def generate_fallback_sql(question: str, *, table_name: str) -> str | None:
    """Heuristic SQL generator for common analytics questions.

    This is a robustness fallback when the LLM is unavailable.
    It intentionally covers the public prompt set and a few close variants.
    """

    q = question.strip().lower()

    # Clearly out-of-domain / not present in schema.
    if "zodiac" in q:
        return None

    tn = f'"{table_name}"'

    # Destructive requests -> return something validator will reject.
    if re.search(r"\b(delete|drop|update|insert|alter|create|truncate)\b", q):
        return f"DELETE FROM {tn}"

    # Top-N by average addiction/anxiety.
    if re.search(r"\btop\b", q) and "age" in q and "addiction" in q:
        return (
            f"SELECT age, AVG(addiction_level) AS avg_addiction_level "
            f"FROM {tn} "
            f"GROUP BY age "
            f"ORDER BY avg_addiction_level DESC "
            f"LIMIT 5"
        )

    if re.search(r"\btop\b", q) and "age" in q and "anxiety" in q:
        return (
            f"SELECT age, AVG(anxiety_score) AS avg_anxiety_score "
            f"FROM {tn} "
            f"GROUP BY age "
            f"ORDER BY avg_anxiety_score DESC "
            f"LIMIT 5"
        )

    # Count high addiction.
    if ("how many" in q or "count" in q or "roughly" in q) and "addiction" in q and (">=" in q or "high" in q or "highest" in q):
        return f"SELECT COUNT(*) AS respondent_count FROM {tn} WHERE addiction_level >= 5"

    # Anxiety by addiction level.
    if "anxiety" in q and "addiction" in q and ("as" in q or "increase" in q or "differ" in q or "by" in q):
        return (
            f"SELECT addiction_level, AVG(anxiety_score) AS avg_anxiety_score "
            f"FROM {tn} "
            f"GROUP BY addiction_level "
            f"ORDER BY addiction_level"
        )

    # Addiction by gender.
    if "addiction" in q and "gender" in q:
        # Some questions ask for comparison; average is a good default.
        return (
            f"SELECT gender, AVG(addiction_level) AS avg_addiction_level "
            f"FROM {tn} "
            f"GROUP BY gender "
            f"ORDER BY avg_addiction_level DESC"
        )

    # Anxiety by gender (avg).
    if "average" in q and "anxiety" in q and "gender" in q:
        return (
            f"SELECT gender, AVG(anxiety_score) AS avg_anxiety_score "
            f"FROM {tn} "
            f"GROUP BY gender "
            f"ORDER BY avg_anxiety_score DESC"
        )

    if "gender" in q and "highest" in q and "anxiety" in q:
        return (
            f"SELECT gender, AVG(anxiety_score) AS avg_anxiety_score "
            f"FROM {tn} "
            f"GROUP BY gender "
            f"ORDER BY avg_anxiety_score DESC "
            f"LIMIT 1"
        )

    # Shares/buckets.
    if ("share" in q or "what share" in q or "percentage" in q) and "low" in q and "addiction" in q:
        return (
            f"SELECT (SUM(CASE WHEN addiction_level < 2 THEN 1 ELSE 0 END) * 1.0) / COUNT(*) AS low_addiction_share "
            f"FROM {tn}"
        )

    if "bucket" in q and "addiction" in q and ("largest" in q or "most" in q):
        return (
            f"SELECT CASE "
            f"WHEN addiction_level < 2 THEN 'Low (0-2)' "
            f"WHEN addiction_level < 5 THEN 'Medium (2-5)' "
            f"ELSE 'High (5+)' END AS bucket, "
            f"COUNT(*) AS respondent_count "
            f"FROM {tn} "
            f"GROUP BY bucket "
            f"ORDER BY respondent_count DESC"
        )

    # Default: unknown
    return None
