import math
from pathlib import Path

import pandas as pd


CSV_PATH = Path(__file__).resolve().parent / "data" / "financial_data.csv"
REQUIRED_COLUMNS = {"報表", "項目", "期間", "數值", "單位"}

PERIODS = {
    "2026 上半年": {
        "income": "2026-01-01至2026-06-30",
        "balance": "2026-06-30",
    },
    "2025 上半年": {
        "income": "2025-01-01至2025-06-30",
        "balance": "2025-06-30",
    },
}


def load_financial_data() -> pd.DataFrame:
    data = pd.read_csv(CSV_PATH)
    missing_columns = REQUIRED_COLUMNS - set(data.columns)
    if missing_columns:
        raise ValueError(f"CSV 缺少必要欄位：{', '.join(sorted(missing_columns))}")

    data["數值"] = pd.to_numeric(data["數值"], errors="coerce")
    return data


def get_amount(
    data: pd.DataFrame,
    report: str,
    item: str,
    period: str,
) -> tuple[float, str]:
    matches = data.loc[
        (data["報表"] == report)
        & (data["項目"] == item)
        & (data["期間"] == period)
    ]

    if len(matches) == 0:
        raise ValueError(
            f"缺少必要資料：{report}／{item}／{period}，無法計算相關指標。"
        )
    if len(matches) > 1:
        raise ValueError(
            f"資料重複：{report}／{item}／{period}，請先核對 CSV。"
        )

    value = matches.iloc[0]["數值"]
    if pd.isna(value):
        raise ValueError(
            f"數值無法轉換為數字：{report}／{item}／{period}。"
        )
    if not math.isfinite(float(value)):
        raise ValueError(f"數值不是有限數字：{report}／{item}／{period}。")

    unit = matches.iloc[0]["單位"]
    if pd.isna(unit) or not str(unit).strip():
        raise ValueError(f"缺少單位：{report}／{item}／{period}。")

    return float(value), str(unit)


def calculate_ratio(
    data: pd.DataFrame,
    period_label: str,
    period: str,
    numerator_report: str,
    numerator_item: str,
    denominator_report: str,
    denominator_item: str,
) -> float:
    numerator, numerator_unit = get_amount(
        data, numerator_report, numerator_item, period
    )
    denominator, denominator_unit = get_amount(
        data, denominator_report, denominator_item, period
    )

    if numerator_unit != denominator_unit:
        raise ValueError(
            f"{period_label} 的「{numerator_item}」與「{denominator_item}」"
            f"單位不一致：{numerator_unit}／{denominator_unit}。"
        )
    if denominator == 0:
        raise ValueError(
            f"{period_label} 的「{denominator_item}」為 0，無法計算比率。"
        )

    return numerator / denominator * 100


def build_analysis_table(data: pd.DataFrame) -> pd.DataFrame:
    income_report = "合併綜合損益表"
    balance_report = "合併資產負債表"
    metrics = [
        (
            "毛利率",
            income_report,
            "營業毛利",
            income_report,
            "營業收入",
        ),
        (
            "營業利益率",
            income_report,
            "營業利益",
            income_report,
            "營業收入",
        ),
        (
            "稅後淨利率",
            income_report,
            "本期淨利",
            income_report,
            "營業收入",
        ),
        (
            "負債比率",
            balance_report,
            "負債總計",
            balance_report,
            "資產總計",
        ),
        (
            "權益比率",
            balance_report,
            "權益總計",
            balance_report,
            "資產總計",
        ),
    ]

    results = {}
    for period_label, dates in PERIODS.items():
        results[period_label] = {}
        for (
            metric,
            numerator_report,
            numerator_item,
            denominator_report,
            denominator_item,
        ) in metrics:
            period = (
                dates["income"]
                if numerator_report == income_report
                else dates["balance"]
            )
            denominator_period = (
                dates["income"]
                if denominator_report == income_report
                else dates["balance"]
            )
            if period != denominator_period:
                raise ValueError(f"{period_label} 的 {metric} 期間不一致。")

            results[period_label][metric] = calculate_ratio(
                data,
                period_label,
                period,
                numerator_report,
                numerator_item,
                denominator_report,
                denominator_item,
            )

    return pd.DataFrame(results).rename_axis("財務指標")


def main() -> None:
    data = load_financial_data()
    analysis = build_analysis_table(data)
    print("財務比率（%）")
    print(analysis.to_string(float_format=lambda value: f"{value:.2f}%"))


if __name__ == "__main__":
    main()
