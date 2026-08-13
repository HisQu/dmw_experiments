"""Write a reader-facing Excel audit workbook for historian-grade analysis."""

from __future__ import annotations

import math
from numbers import Real
from pathlib import Path
from typing import Any, cast

import pandas as pd
import xlsxwriter

from dmw_experiments.studies.haiu_comparison.analysis.quality.errors import (
    QualityErrorAnalysis,
)
from dmw_experiments.studies.haiu_comparison.analysis.quality.grades import (
    QualityGradeAnalysis,
)


def export_quality_grade_analysis_workbook(
    *,
    analysis: QualityGradeAnalysis,
    path: Path,
    quality_review_workbook: Path,
    quality_reveal_key: Path,
    error_analysis: QualityErrorAnalysis | None = None,
) -> Path:
    """Export all grade calculations next to the derived quality figures.

    :param analysis: Validated descriptive and paired calculation tables.
    :param path: New ``.xlsx`` audit workbook path.
    :param quality_review_workbook: Source reviewer workbook; only its file
        name is recorded to avoid host-specific paths.
    :param quality_reveal_key: Source condition-reveal key; only its file name
        is recorded to avoid host-specific paths.
    :param error_analysis: Optional false-assignment count calculations from
        the same review workbook.
    :return: The written workbook path.
    :raises FileExistsError: If the target workbook already exists.
    """
    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(
            f"Quality-grade analysis workbook already exists: {resolved}"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with xlsxwriter.Workbook(resolved) as workbook:
        formats = _formats(workbook)
        _write_read_me(
            workbook,
            formats=formats,
            analysis=analysis,
            quality_review_workbook=quality_review_workbook,
            quality_reveal_key=quality_reveal_key,
            error_analysis=error_analysis,
        )
        tables: tuple[tuple[str, pd.DataFrame], ...] = (
            ("01_Graded_Observations", analysis.observations),
            ("02_Condition_Summary", analysis.condition_summary),
            ("03_Grade_Distribution", analysis.grade_distribution),
            (
                "03B_Paired_Grade_Distribution",
                analysis.paired_grade_distribution,
            ),
            (
                "04_False_Assignment_Incidence",
                analysis.false_assignment_pair_summary,
            ),
            ("05_Direct_Duels", analysis.direct_duel_summary),
            ("06_Duel_Pairs", analysis.direct_duel_pairs),
            (
                "06B_Pooled_Grade_Changes",
                analysis.pooled_grade_change_distribution,
            ),
            (
                "06C_Pooled_Grade_Magnitude",
                analysis.pooled_grade_change_magnitude_distribution,
            ),
            ("07_Complete_Triplets", analysis.complete_triplets),
            ("08_Provider_Summary", analysis.provider_summary),
            ("09_Provider_Interaction", analysis.provider_interaction_summary),
            (
                "09B_Provider_Grade_Trends",
                analysis.provider_interaction_trend_summary,
            ),
            (
                "09C_False_Assign_Interaction",
                analysis.provider_false_assignment_interaction_summary,
            ),
            ("10_Provider_Pairs", analysis.provider_interaction_pairs),
            ("11_Exploratory_Friedman", analysis.friedman_summary),
        )
        if error_analysis is not None:
            tables += (
                ("13_Error_Count_Inputs", error_analysis.observations),
                ("14_Error_Count_Coverage", error_analysis.study_overview),
                (
                    "15_Matched_Interpretation_Pairs",
                    error_analysis.matched_interpretation_pairs,
                ),
                (
                    "16_Matched_Assertion_Pairs",
                    error_analysis.matched_assertion_pairs,
                ),
                (
                    "17_Pooled_Interp_Incidence",
                    error_analysis.pooled_interpretation_incidence,
                ),
                (
                    "18_Pooled_Assert_Incidence",
                    error_analysis.pooled_assertion_incidence,
                ),
                (
                    "19_Interp_Pair_Differences",
                    error_analysis.interpretation_pair_differences,
                ),
                (
                    "20_Assert_Pair_Differences",
                    error_analysis.assertion_pair_differences,
                ),
                (
                    "21_Pooled_Interp_Changes",
                    error_analysis.pooled_interpretation_change_distribution,
                ),
                (
                    "21B_Pooled_Interp_Magnitude",
                    error_analysis.pooled_interpretation_change_magnitude_distribution,
                ),
                (
                    "22_Pooled_Assert_Changes",
                    error_analysis.pooled_assertion_change_distribution,
                ),
                (
                    "22B_Pooled_Assert_Magnitude",
                    error_analysis.pooled_assertion_change_magnitude_distribution,
                ),
            )
        for index, (sheet_name, table) in enumerate(tables, start=1):
            _write_dataframe_sheet(
                workbook,
                sheet_name=sheet_name,
                table=table,
                table_name=f"QualityGradeTable{index}",
                formats=formats,
            )
        _write_methods_sheet(
            workbook,
            formats=formats,
            has_error_analysis=error_analysis is not None,
        )
    return resolved


def _formats(workbook: Any) -> dict[str, Any]:
    """Create the small, consistent set of reader-facing workbook formats.

    :param workbook: Target workbook that owns the formats.
    :return: Named XlsxWriter formats used by the audit sheets.
    """
    return {
        "title": workbook.add_format(
            {
                "bold": True,
                "font_size": 16,
                "font_color": "#1F1F1F",
                "bg_color": "#D9EAF7",
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "section": workbook.add_format(
            {
                "bold": True,
                "font_color": "#1F1F1F",
                "bg_color": "#EAF2F8",
                "valign": "top",
            }
        ),
        "body": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "integer": workbook.add_format({"num_format": "0"}),
        "decimal": workbook.add_format({"num_format": "0.00"}),
        "percent": workbook.add_format({"num_format": "0%"}),
        "header": workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#1F4E78",
                "text_wrap": True,
                "valign": "top",
            }
        ),
    }


def _write_read_me(
    workbook: Any,
    *,
    formats: dict[str, Any],
    analysis: QualityGradeAnalysis,
    quality_review_workbook: Path,
    quality_reveal_key: Path,
    error_analysis: QualityErrorAnalysis | None,
) -> None:
    """Write scope, population, and source information before data tables.

    :param workbook: Workbook receiving the explanatory first worksheet.
    :param formats: Shared workbook formats.
    :param analysis: Completed grade calculation tables.
    :param quality_review_workbook: Completed historian-review source workbook.
    :param quality_reveal_key: Condition-reveal source JSON file.
    :param error_analysis: Optional false-assignment count calculations from
        the same review workbook.
    :return: ``None`` after writing the sheet.
    """
    sheet = workbook.add_worksheet("00_Read_Me")
    sheet.set_column("A:A", 28)
    sheet.set_column("B:B", 96)
    sheet.merge_range(
        "A1:B1",
        "Historian quality-grade analysis audit",
        formats["title"],
    )
    rows: tuple[tuple[str, str], ...] = (
        (
            "Purpose",
            "Auditable descriptive and matched calculations behind the paired "
            "historian-quality figures. Lower grades are better.",
        ),
        (
            "Source review workbook",
            quality_review_workbook.name,
        ),
        (
            "Source reveal key",
            quality_reveal_key.name,
        ),
        (
            "Selection rule",
            "Includes populated grades after applying the reveal key. Quality "
            "therefore remains conditional on the review population, not on "
            "all attempted experiment outputs.",
        ),
        (
            "Grade scale",
            "Whole ordinal values: 1 = best and 6 = worst. Means and sample "
            "standard deviations are descriptive summaries, not interval-scale "
            "effect estimates.",
        ),
        (
            "Direct duels",
            "Only rows where both named conditions have a grade for the same "
            "provider and regest. The lower grade wins; equal grades tie.",
        ),
        (
            "Outright best",
            "Only a strict lowest grade within a complete three-condition "
            "provider/regest triplet. Tied minima receive no winner.",
        ),
        (
            "Provider interaction",
            "Only regesta complete for all three conditions in both providers. "
            "The grade row reports descriptive means with paired-bootstrap "
            "95% intervals and a two-sided exact paired sign test. The false-"
            "assignment row reports Wilson rate intervals and an exact paired "
            "McNemar test. Both are exploratory and do not establish a backend "
            "cause.",
        ),
        (
            "Exploratory Friedman test",
            "Ranks the three conditions within each complete provider/regest "
            "triplet and applies a tie correction. It is not publication-grade "
            "inference because the grade scale is ordinal and observations are "
            "not an independent random sample.",
        ),
    )
    if error_analysis is not None:
        rows += (
            (
                "False-assignment count analysis",
                "The later error-count sheets retain optional reviewer fields "
                "without replacing missing values by zero. They cover "
                f"{len(error_analysis.observations)} reviews with at least "
                "one count. Their profile calculations use direct "
                "provider–regest pairs separately for interpretation and "
                "assertion counts, then pool those valid provider-local "
                "pairs for the figure. They distinguish literal incorrect "
                "assertions from the independent misunderstandings that "
                "caused them.",
            ),
        )
    sheet.write_row("A3", ("Item", "Explanation"), formats["header"])
    for row_index, row in enumerate(rows, start=3):
        sheet.write(row_index, 0, row[0], formats["section"])
        sheet.write(row_index, 1, row[1], formats["body"])
    overview_start = len(rows) + 5
    sheet.write_row(
        overview_start,
        0,
        ("Population measure", "Value"),
        formats["header"],
    )
    for offset, row in enumerate(
        analysis.study_overview.itertuples(index=False, name=None),
        start=1,
    ):
        sheet.write(overview_start + offset, 0, row[0], formats["section"])
        sheet.write(overview_start + offset, 1, row[1], formats["integer"])
    sheet.freeze_panes(3, 0)


def _write_dataframe_sheet(
    workbook: Any,
    *,
    sheet_name: str,
    table: pd.DataFrame,
    table_name: str,
    formats: dict[str, Any],
) -> None:
    """Write one typed calculation table with filters and frozen headers.

    :param workbook: Workbook receiving the worksheet.
    :param sheet_name: Excel worksheet name.
    :param table: Calculation table to write.
    :param table_name: Unique Excel table identifier.
    :param formats: Shared workbook formats.
    :return: ``None`` after writing the data and its reader aids.
    """
    sheet = workbook.add_worksheet(sheet_name)
    columns = list(table.columns)
    sheet.freeze_panes(1, 0)
    for column_index, column in enumerate(columns):
        sheet.write(0, column_index, column, formats["header"])
        sheet.set_column(
            column_index,
            column_index,
            _column_width(column, cast(pd.Series, table[column])),
            _column_format(column, formats),
        )
    for row_index, row in enumerate(
        table.itertuples(index=False, name=None),
        start=1,
    ):
        for column_index, value in enumerate(row):
            sheet.write(
                row_index,
                column_index,
                _excel_value(value),
                _column_format(columns[column_index], formats),
            )
    if columns and not table.empty:
        sheet.add_table(
            0,
            0,
            len(table),
            len(columns) - 1,
            {
                "name": table_name,
                "style": "Table Style Medium 2",
                "columns": [
                    {
                        "header": column,
                        "format": _column_format(column, formats),
                    }
                    for column in columns
                ],
            },
        )
    _apply_grade_scale(sheet, table=table)


def _write_methods_sheet(
    workbook: Any,
    *,
    formats: dict[str, Any],
    has_error_analysis: bool,
) -> None:
    """Record exact calculation rules beside the derived evidence tables.

    :param workbook: Workbook receiving the methods worksheet.
    :param formats: Shared workbook formats.
    :param has_error_analysis: Whether this export includes count-derived
        false-assignment tables.
    :return: ``None`` after writing the sheet.
    """
    sheet = workbook.add_worksheet("12_Methods")
    sheet.set_column("A:A", 28)
    sheet.set_column("B:B", 90)
    sheet.set_column("C:C", 42)
    sheet.write_row(
        "A1",
        ("Calculation", "Definition", "Where to audit it"),
        formats["header"],
    )
    rows: tuple[tuple[str, str, str], ...] = (
        (
            "Condition mean and median",
            "Arithmetic mean and median over all graded models for one "
            "condition. Lower is better. These summarize an ordinal scale "
            "descriptively and do not prove a condition effect.",
            "02_Condition_Summary; source rows in 01_Graded_Observations",
        ),
        (
            "Grade distribution",
            "Count and share of each whole grade 1–6 within a condition. "
            "Shares use the condition's graded-model denominator.",
            "03_Grade_Distribution",
        ),
        (
            "Practical review categories",
            "Grades 1–3 contain no clearly false assignments: grade 1 is "
            "essentially complete, grade 2 has only minor omissions or "
            "defensible simplifications, and grade 3 is materially incomplete "
            "but factually safe. Grade 4 is a bounded local or formal error "
            "with the central historical proposition intact; grade 5 is "
            "plausible but materially false historical misinformation; grade 6 "
            "is a gross source-reading failure. The 3–4 and 5–6 aggregates are "
            "descriptive only; use individual grades for review decisions.",
            "02_Condition_Summary",
        ),
        (
            "False-assignment incidence and Wilson interval",
            "A grade of 4–6 records at least one clearly false assignment by "
            "the review rubric. The share is false_assignment_count / models "
            "within one provider, matched direct comparison, and condition. "
            "Both condition rows in a comparison use the same complete "
            "provider–regest pairs. The two-sided 95% Wilson score interval "
            "gives the uncertainty bounds for that binomial share.",
            "04_False_Assignment_Incidence",
        ),
        (
            "Direct duel",
            "For a provider/regest with both grades, lower is better. "
            "first_minus_second_grade < 0 means the first condition won; "
            "0 is a tie; > 0 means the second condition won.",
            "05_Direct_Duels and 06_Duel_Pairs",
        ),
        (
            "Pooled paired grade changes",
            "Across all already valid provider-local direct pairs, lower grade "
            "in the right condition means improved, equal grade unchanged, and "
            "higher grade worsened. Each direct-comparison denominator is the "
            "number of complete provider–regest grade pairs.",
            "06B_Pooled_Grade_Changes",
        ),
        (
            "Paired grade-change magnitude",
            "Using the same matched denominator, divide improvements and "
            "worsenings into exact 1-grade, exact 2-grade, and greater-than-2-"
            "grade categories around unchanged pairs. Zero-count categories "
            "remain visible so every comparison has the same seven bins.",
            "06C_Pooled_Grade_Magnitude",
        ),
        (
            "Paired grade distribution",
            "Count and share of each whole grade 1–6 at each endpoint of a "
            "planned direct comparison. The two DMW + Haiu RAG endpoint "
            "groups show the same condition but retain the distinct valid "
            "provider–regest populations of the adjacent comparisons.",
            "03B_Paired_Grade_Distribution",
        ),
        (
            "Outright best",
            "A condition receives one win only when it is the sole lowest "
            "grade in a complete three-condition provider/regest triplet. "
            "Tied minima are recorded as tie.",
            "07_Complete_Triplets and 02_Condition_Summary",
        ),
        (
            "Provider interaction",
            "Pairs only regesta with all three condition grades in both "
            "providers. first_minus_second_grade < 0 means the first provider "
            "received the better lower grade. The two-sided exact sign test "
            "uses only non-tied paired regesta, so it respects the ordinal "
            "grade scale and does not treat grade distance as interval data. "
            "The plotted descriptive means have paired-bootstrap 95% "
            "intervals, created by resampling both provider margins together.",
            "09_Provider_Interaction, 09B_Provider_Grade_Trends, and "
            "10_Provider_Pairs",
        ),
        (
            "Provider false-assignment interaction",
            "Within the same complete provider/regest pairs, grades 4–6 are "
            "converted to an indicator for one or more false assignments. "
            "Each provider's marginal rate has a two-sided 95% Wilson score "
            "interval. The exact two-sided McNemar test uses only discordant "
            "provider pairs, respecting the paired binary design.",
            "09C_False_Assign_Interaction",
        ),
        (
            "Exploratory Friedman χ²",
            "Within each complete triplet, rank the three grades with average "
            "ranks for ties. Apply the standard tie correction. The reported "
            "p value is the χ²(df=2) asymptotic survival function.",
            "11_Exploratory_Friedman",
        ),
    )
    if has_error_analysis:
        rows += (
            (
                "Matched error-count populations",
                "Each false-assignment profile comparison retains only "
                "provider–regest pairs with an entered value for both named "
                "conditions. Interpretation and assertion counts use separate "
                "pair populations because either optional field may be blank. "
                "The profile pools those already matched provider-local pairs; "
                "it does not pair AcademicCloud rows to LM Studio rows.",
                "15_Matched_Interpretation_Pairs and "
                "16_Matched_Assertion_Pairs",
            ),
            (
                "Independent false-interpretation incidence",
                "After pooling provider-local direct pairs, count the mutually "
                "exclusive 0, 1, 2, and 3+ bands. The any-error share is the "
                "sum of the 1, 2, and 3+ bands, using the shared paired "
                "denominator.",
                "17_Pooled_Interp_Incidence",
            ),
            (
                "False atomic assertion incidence",
                "After pooling provider-local direct pairs, count the exact "
                "false atomic assertions in the mutually exclusive 0, 1, 2, "
                "3, and 4+ bands. It is a count distribution, not a normalized "
                "error rate per substantive assertion.",
                "18_Pooled_Assert_Incidence",
            ),
            (
                "Paired error-count difference",
                "For every direct provider–regest pair, subtract the first "
                "condition's count from the second condition's count. A "
                "negative value means fewer errors in the right condition "
                "(improved); a positive value means more errors (worsened). "
                "For independent false interpretations, the 3+ review band "
                "uses its lower bound of 3. A magnitude category involving "
                "3+ is therefore conservative, and two 3+ endpoints need not "
                "have equal exact counts.",
                "19_Interp_Pair_Differences and 20_Assert_Pair_Differences",
            ),
            (
                "Paired change distribution",
                "For each direct comparison, count and divide by all matched "
                "provider–regest pairs that improved, were unchanged, or "
                "worsened. The figure stacks these mutually exclusive shares "
                "to show how often changing condition helped or harmed the "
                "same regest.",
                "21_Pooled_Interp_Changes and 22_Pooled_Assert_Changes",
            ),
            (
                "Paired error-change magnitude",
                "Using the same matched denominator, divide fewer-error and "
                "more-error pairs into exact 1-error, exact 2-error, and "
                "greater-than-2-error categories around unchanged pairs. "
                "Interpretation magnitudes use 3 as the recorded lower bound "
                "for 3+; assertion magnitudes use exact reviewer counts.",
                "21B_Pooled_Interp_Magnitude and 22B_Pooled_Assert_Magnitude",
            ),
        )
    for row_index, row in enumerate(rows, start=1):
        sheet.write(row_index, 0, row[0], formats["section"])
        sheet.write(row_index, 1, row[1], formats["body"])
        sheet.write(row_index, 2, row[2], formats["body"])
    sheet.freeze_panes(1, 0)


def _column_width(column: str, values: pd.Series) -> float:
    """Choose a compact, readable width without excessive horizontal scroll.

    :param column: Column header text.
    :param values: Values displayed under that header.
    :return: Excel character width between practical lower and upper bounds.
    """
    examples = [str(value) for value in values.head(100) if pd.notna(value)]
    longest = max(
        [len(column), *(len(value) for value in examples)], default=12
    )
    return float(min(max(longest + 2, 12), 36))


def _column_format(
    column: str,
    formats: dict[str, Any],
) -> Any:
    """Choose a number format from stable calculation-column names.

    :param column: Calculation-table column name.
    :param formats: Shared workbook formats.
    :return: Format appropriate for the column's semantic value.
    """
    if column.endswith("_share"):
        return formats["percent"]
    if (
        "mean" in column
        or "median" in column
        or "sd" in column
        or "chi_square" in column
        or "tie_correction" in column
        or "p_value" in column
    ):
        return formats["decimal"]
    if (
        column == "grade"
        or column.endswith("_grade")
        or column.endswith("_count")
        or column in {"models", "providers", "unique_regesta", "complete_pairs"}
    ):
        return formats["integer"]
    return formats["body"]


def _excel_value(value: object) -> Any:
    """Replace pandas missing values with empty Excel cells.

    :param value: Dataframe cell value.
    :return: Original scalar or ``None`` for a missing spreadsheet value.
    """
    if value is None or value is pd.NA:
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        return None if math.isnan(float(value)) else value
    return value


def _apply_grade_scale(
    sheet: Any,
    *,
    table: pd.DataFrame,
) -> None:
    """Add a clear low-good/high-bad color scale to grade columns.

    :param sheet: Worksheet that owns the data table.
    :param table: Source dataframe used to identify grade columns.
    :return: ``None`` after conditional formatting.
    """
    for column_index, column in enumerate(table.columns):
        if column == "grade" or column.endswith("_grade"):
            sheet.conditional_format(
                1,
                column_index,
                max(len(table), 1),
                column_index,
                {
                    "type": "3_color_scale",
                    "min_color": "#63BE7B",
                    "mid_color": "#FFEB84",
                    "max_color": "#F8696B",
                },
            )
