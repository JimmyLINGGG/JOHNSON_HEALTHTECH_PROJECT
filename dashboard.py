import math
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import financial_analysis as analysis


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = BASE_DIR / "data" / "financial_data.csv"

INCOME_REPORT = "合併綜合損益表"
BALANCE_REPORT = "合併資產負債表"
CASH_FLOW_REPORT = "合併現金流量表"
INCOME_ITEMS = ["營業收入", "營業毛利", "營業利益", "本期淨利"]
BALANCE_ITEMS = [
    "現金及約當現金",
    "應收帳款淨額",
    "存貨",
    "資產總計",
    "負債總計",
    "權益總計",
]
CASH_FLOW_ITEMS = [
    "營業活動現金流量",
    "投資活動現金流量",
    "籌資活動現金流量",
]
MARGIN_ITEMS = ["毛利率", "營業利益率", "稅後淨利率"]
AMOUNT_LABELS = {
    "營業收入": "營收",
    "營業毛利": "毛利",
    "營業利益": "營業利益",
    "本期淨利": "稅後淨利",
}
METRIC_LABELS = {
    "毛利率": "毛利率",
    "營業利益率": "營業利益率",
    "稅後淨利率": "稅後淨利率",
}
CHART_COLORS = {
    "2026 上半年": "#35D0BA",
    "2025 上半年": "#8A9BB8",
    "資產總計": "#35D0BA",
    "負債總計": "#F58A6E",
    "權益總計": "#8A9BB8",
    "現金及約當現金": "#35D0BA",
    "應收帳款淨額": "#6EA8FE",
    "存貨": "#C792EA",
    "營業活動現金流量": "#35D0BA",
    "投資活動現金流量": "#F5B85C",
    "籌資活動現金流量": "#8A9BB8",
}
REQUIRED_COLUMNS = {"報表", "項目", "期間", "數值", "單位"}


def validate_data(data: pd.DataFrame) -> pd.DataFrame:
    missing_columns = REQUIRED_COLUMNS - set(data.columns)
    if missing_columns:
        raise ValueError(f"CSV 缺少必要欄位：{', '.join(sorted(missing_columns))}")

    clean_data = data.copy()
    numeric_values = pd.to_numeric(clean_data["數值"], errors="coerce")
    invalid_values = numeric_values.isna() | ~numeric_values.map(
        lambda value: math.isfinite(value) if pd.notna(value) else False
    )
    if invalid_values.any():
        rows = (clean_data.index[invalid_values] + 2).tolist()
        raise ValueError(
            "「數值」欄含空值、非數字或無限值；"
            f"請檢查 CSV 第 {', '.join(map(str, rows[:10]))} 列。"
        )
    clean_data["數值"] = numeric_values

    missing_units = clean_data["單位"].isna() | clean_data["單位"].astype(
        str
    ).str.strip().eq("")
    if missing_units.any():
        rows = (clean_data.index[missing_units] + 2).tolist()
        raise ValueError(
            f"CSV 缺少單位，請檢查第 {', '.join(map(str, rows[:10]))} 列。"
        )

    key_columns = ["報表", "項目", "期間"]
    duplicate_rows = clean_data.duplicated(subset=key_columns, keep=False)
    if duplicate_rows.any():
        examples = clean_data.loc[duplicate_rows, key_columns].head(5)
        details = "；".join(
            "／".join(map(str, row)) for row in examples.itertuples(index=False)
        )
        raise ValueError(f"資料存在重複的報表／項目／期間：{details}")

    required_items = {
        INCOME_REPORT: INCOME_ITEMS,
        BALANCE_REPORT: BALANCE_ITEMS,
        CASH_FLOW_REPORT: CASH_FLOW_ITEMS,
    }
    for period_label, dates in analysis.PERIODS.items():
        for report, items in required_items.items():
            period_key = (
                "balance" if report == BALANCE_REPORT else "income"
            )
            period = dates[period_key]
            for item in items:
                analysis.get_amount(clean_data, report, item, period)

        balance_date = dates["balance"]
        assets, _ = analysis.get_amount(
            clean_data, BALANCE_REPORT, "資產總計", balance_date
        )
        liabilities, _ = analysis.get_amount(
            clean_data, BALANCE_REPORT, "負債總計", balance_date
        )
        equity, _ = analysis.get_amount(
            clean_data, BALANCE_REPORT, "權益總計", balance_date
        )
        if not math.isclose(assets, liabilities + equity, abs_tol=1):
            raise ValueError(
                f"{period_label} 資產負債表不平衡："
                f"資產 {assets:,.0f}，負債加權益 {liabilities + equity:,.0f}。"
            )

    result = analysis.build_analysis_table(clean_data)
    for metric in MARGIN_ITEMS + ["負債比率", "權益比率"]:
        metric_units = set()
        for dates in analysis.PERIODS.values():
            if metric in MARGIN_ITEMS:
                report = INCOME_REPORT
                period = dates["income"]
                numerator_item = {
                    "毛利率": "營業毛利",
                    "營業利益率": "營業利益",
                    "稅後淨利率": "本期淨利",
                }[metric]
                denominator_item = "營業收入"
            else:
                report = BALANCE_REPORT
                period = dates["balance"]
                numerator_item = "負債總計" if metric == "負債比率" else "權益總計"
                denominator_item = "資產總計"

            _, numerator_unit = analysis.get_amount(
                clean_data, report, numerator_item, period
            )
            _, denominator_unit = analysis.get_amount(
                clean_data, report, denominator_item, period
            )
            if numerator_unit != denominator_unit:
                raise ValueError(
                    f"{period} 的「{numerator_item}」與「{denominator_item}」"
                    "單位不一致，無法計算比率。"
                )
            metric_units.add(numerator_unit)

        if len(metric_units) != 1:
            raise ValueError(f"{metric} 的 2025 與 2026 單位不一致，無法比較。")

    for report, items, period_key in [
        (INCOME_REPORT, INCOME_ITEMS, "income"),
        (BALANCE_REPORT, BALANCE_ITEMS, "balance"),
        (CASH_FLOW_REPORT, CASH_FLOW_ITEMS, "income"),
    ]:
        for item in items:
            units = set()
            for dates in analysis.PERIODS.values():
                _, unit = analysis.get_amount(
                    clean_data, report, item, dates[period_key]
                )
                units.add(unit)
            if len(units) != 1:
                raise ValueError(f"「{item}」的 2025 與 2026 單位不一致，無法比較。")

    return clean_data


def build_comparison_table(
    data: pd.DataFrame,
    report: str,
    items: list,
    period_key: str,
) -> Tuple[pd.DataFrame, str]:
    values = {}
    units = set()
    for item in items:
        values[item], unit = get_period_amounts(data, report, item, period_key)
        units.add(unit)
    if len(units) != 1:
        raise ValueError(f"{report} 欄位單位不一致，無法比較。")

    table = pd.DataFrame(values).T
    table.index.name = "項目"
    table["年增額"] = table["2026 上半年"] - table["2025 上半年"]
    table["年增率"] = table.apply(
        lambda row: (
            row["年增額"] / row["2025 上半年"] * 100
            if row["2025 上半年"] != 0
            else float("nan")
        ),
        axis=1,
    )
    return table, units.pop()


def get_source_pages(
    data: pd.DataFrame, report: str, item: str, period: str
) -> str:
    matches = data.loc[
        (data["報表"] == report)
        & (data["項目"] == item)
        & (data["期間"] == period),
        "PDF頁碼",
    ]
    if matches.empty or pd.isna(matches.iloc[0]):
        return "待確認"
    return f"第 {int(matches.iloc[0])} 頁"


def get_period_amounts(
    data: pd.DataFrame, report: str, item: str, period_key: str
) -> Tuple[Dict[str, float], str]:
    values = {}
    units = set()
    for label, dates in analysis.PERIODS.items():
        value, unit = analysis.get_amount(
            data, report, item, dates[period_key]
        )
        values[label] = value
        units.add(unit)
    if len(units) != 1:
        raise ValueError(f"「{item}」的比較單位不一致。")
    return values, units.pop()


def make_margin_chart(ratios: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for year in analysis.PERIODS:
        figure.add_trace(
            go.Bar(
                name=year,
                x=[METRIC_LABELS[item] for item in MARGIN_ITEMS],
                y=[ratios.loc[item, year] for item in MARGIN_ITEMS],
                text=[f"{ratios.loc[item, year]:.2f}%" for item in MARGIN_ITEMS],
                textposition="outside",
                marker_color=CHART_COLORS[year],
                hovertemplate="%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        height=360,
        yaxis_title="比率（%）",
        yaxis_ticksuffix="%",
        legend_title_text="比較期間",
        margin=dict(t=25, b=20),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def make_amount_chart(data: pd.DataFrame) -> Tuple[go.Figure, str]:
    values_by_item = {}
    for item in INCOME_ITEMS:
        values, unit = get_period_amounts(data, INCOME_REPORT, item, "income")
        values_by_item[item] = values

    units = {
        analysis.get_amount(data, INCOME_REPORT, item, dates["income"])[1]
        for item in INCOME_ITEMS
        for dates in analysis.PERIODS.values()
    }
    if len(units) != 1:
        raise ValueError("營收、毛利、營業利益與淨利的單位不一致，無法放在同一圖表。")
    unit = units.pop()

    figure = go.Figure()
    for year in analysis.PERIODS:
        figure.add_trace(
            go.Bar(
                name=year,
                x=[AMOUNT_LABELS[item] for item in INCOME_ITEMS],
                y=[values_by_item[item][year] for item in INCOME_ITEMS],
                text=[
                    f"{values_by_item[item][year]:,.0f}"
                    for item in INCOME_ITEMS
                ],
                textposition="outside",
                marker_color=CHART_COLORS[year],
                hovertemplate="%{x}<br>%{y:,.0f}<extra>%{fullData.name}</extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        height=380,
        yaxis_title=f"金額（{unit}）",
        yaxis_tickformat=",",
        legend_title_text="比較期間",
        margin=dict(t=25, b=20),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure, unit


def make_balance_chart(data: pd.DataFrame) -> go.Figure:
    liabilities = []
    equity = []
    for year, dates in analysis.PERIODS.items():
        assets, _ = analysis.get_amount(
            data, BALANCE_REPORT, "資產總計", dates["balance"]
        )
        debt, _ = analysis.get_amount(
            data, BALANCE_REPORT, "負債總計", dates["balance"]
        )
        owners_equity, _ = analysis.get_amount(
            data, BALANCE_REPORT, "權益總計", dates["balance"]
        )
        if assets <= 0:
            raise ValueError(f"{year} 資產總計必須大於 0，無法計算結構比率。")
        liabilities.append(debt / assets * 100)
        equity.append(owners_equity / assets * 100)

    figure = go.Figure(
        data=[
            go.Bar(
                name="負債比率",
                x=list(analysis.PERIODS),
                y=liabilities,
                text=[f"{value:.2f}%" for value in liabilities],
                textposition="inside",
                marker_color=CHART_COLORS["負債總計"],
                hovertemplate="%{x}<br>負債比率：%{y:.2f}%<extra></extra>",
            ),
            go.Bar(
                name="權益比率",
                x=list(analysis.PERIODS),
                y=equity,
                text=[f"{value:.2f}%" for value in equity],
                textposition="inside",
                marker_color=CHART_COLORS["權益總計"],
                hovertemplate="%{x}<br>權益比率：%{y:.2f}%<extra></extra>",
            ),
        ]
    )
    figure.update_layout(
        barmode="stack",
        height=350,
        yaxis=dict(title="占總資產比率（%）", ticksuffix="%", range=[0, 100]),
        legend_title_text="資產來源",
        margin=dict(t=25, b=20),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def make_amount_comparison_chart(
    data: pd.DataFrame,
    report: str,
    items: list,
    period_key: str,
    labels: Dict[str, str],
    colors: Dict[str, str] = None,
) -> Tuple[go.Figure, str]:
    table, unit = build_comparison_table(data, report, items, period_key)
    figure = go.Figure()
    for item in items:
        figure.add_trace(
            go.Bar(
                name=labels.get(item, item),
                x=list(analysis.PERIODS),
                y=[table.loc[item, year] for year in analysis.PERIODS],
                text=[f"{table.loc[item, year]:,.0f}" for year in analysis.PERIODS],
                textposition="outside",
                marker_color=(colors or {}).get(item),
                hovertemplate=(
                    f"{labels.get(item, item)}<br>%{{x}}<br>"
                    "%{y:,.0f}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        barmode="group",
        height=370,
        yaxis_title=f"金額（{unit}）",
        yaxis_tickformat=",",
        legend_title_text="財務項目",
        margin=dict(t=25, b=20),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure, unit


def make_margin_comparison_chart(ratios: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for metric in MARGIN_ITEMS:
        current = ratios.loc[metric, "2026 上半年"]
        prior = ratios.loc[metric, "2025 上半年"]
        figure.add_trace(
            go.Bar(
                name=METRIC_LABELS[metric],
                x=["2025 上半年", "2026 上半年"],
                y=[prior, current],
                text=[f"{prior:.2f}%", f"{current:.2f}%"],
                textposition="outside",
                marker_color=CHART_COLORS["2026 上半年"],
                hovertemplate="%{x}<br>%{y:.2f}%<extra>%{fullData.name}</extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        height=360,
        yaxis_title="比率（%）",
        yaxis_ticksuffix="%",
        legend_title_text="獲利指標",
        margin=dict(t=25, b=20),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def apply_enterprise_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
            --surface: #111a2b;
            --surface-raised: #172338;
            --border: rgba(159, 180, 211, 0.13);
            --muted: #91a1bb;
            --accent: #35d0ba;
        }
        .stApp {
            background:
                radial-gradient(ellipse at 82% -10%, rgba(35, 83, 111, .22), transparent 35%),
                #0a1020;
        }
        [data-testid="stHeader"] { background: rgba(10, 16, 32, .82); }
        [data-testid="stSidebar"] {
            background: #0e1728;
            border-right: 1px solid var(--border);
        }
        .block-container { max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem; }
        h1, h2, h3 { letter-spacing: -.025em; }
        h1 { font-size: 2.1rem !important; }
        h2 { font-size: 1.25rem !important; }
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #17243a, #111a2b);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px 20px;
            min-height: 132px;
        }
        [data-testid="stMetricLabel"] p { color: var(--muted); font-size: .88rem; }
        [data-testid="stMetricValue"] { font-size: 1.55rem; }
        [data-testid="stMetricDelta"] { font-size: .83rem; }
        [data-testid="stPlotlyChart"] {
            background: linear-gradient(145deg, rgba(23, 35, 56, .78), rgba(17, 26, 43, .85));
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 8px 10px 0;
        }
        [data-testid="stDataFrame"], [data-testid="stExpander"] {
            border: 1px solid var(--border);
            border-radius: 12px;
        }
        [data-testid="stTabs"] button { font-weight: 600; }
        .eyebrow {
            color: var(--accent);
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .14em;
            text-transform: uppercase;
        }
        .subtitle { color: var(--muted); font-size: .96rem; }
        .section-note { color: var(--muted); font-size: .83rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="喬山健康科技｜企業財務分析",
        page_icon="J",
        layout="wide",
    )
    apply_enterprise_theme()
    st.markdown('<div class="eyebrow">JOHNSON HEALTH TECH · FINANCIAL INTELLIGENCE</div>', unsafe_allow_html=True)
    st.title("企業財務分析")
    st.markdown(
        '<div class="subtitle">喬山健康科技（1736）｜2026 vs 2025 上半年合併財務</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### 資料來源")
        uploaded_file = st.file_uploader(
            "上傳財務資料 CSV",
            type=["csv"],
            help="請使用包含報表、項目、期間、數值與單位欄位的 CSV。",
        )
        if uploaded_file is None:
            if not DEFAULT_CSV_PATH.exists():
                st.error(f"找不到預設資料檔：{DEFAULT_CSV_PATH}")
                st.stop()
            try:
                raw_data = pd.read_csv(DEFAULT_CSV_PATH)
            except (OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
                st.error(f"讀取預設 CSV 失敗：{error}")
                st.stop()
            source_name = "data/financial_data.csv"
        else:
            try:
                raw_data = pd.read_csv(uploaded_file)
            except (UnicodeDecodeError, pd.errors.ParserError) as error:
                st.error(f"讀取上傳 CSV 失敗：{error}")
                st.stop()
            source_name = uploaded_file.name

    try:
        data = validate_data(raw_data)
        ratios = analysis.build_analysis_table(data)
        amount_figure, unit = make_amount_chart(data)
        margin_figure = make_margin_chart(ratios)
        balance_figure, balance_unit = make_amount_comparison_chart(
            data,
            BALANCE_REPORT,
            ["資產總計", "負債總計", "權益總計"],
            "balance",
            {
                "資產總計": "資產總計",
                "負債總計": "負債總計",
                "權益總計": "權益總計",
            },
            CHART_COLORS,
        )
        asset_detail_figure, _ = make_amount_comparison_chart(
            data,
            BALANCE_REPORT,
            ["現金及約當現金", "應收帳款淨額", "存貨"],
            "balance",
            {
                "現金及約當現金": "現金及約當現金",
                "應收帳款淨額": "應收帳款",
                "存貨": "存貨",
            },
            CHART_COLORS,
        )
        cash_flow_figure, cash_flow_unit = make_amount_comparison_chart(
            data,
            CASH_FLOW_REPORT,
            CASH_FLOW_ITEMS,
            "income",
            {
                "營業活動現金流量": "營業活動",
                "投資活動現金流量": "投資活動",
                "籌資活動現金流量": "籌資活動",
            },
            CHART_COLORS,
        )
        margin_comparison_figure = make_margin_comparison_chart(ratios)
    except ValueError as error:
        st.error(f"無法建立 Dashboard：{error}")
        st.info("請確認 CSV 期間、報表項目、數值及單位與財務資料表格式一致。")
        st.stop()

    st.markdown(
        f'<div class="section-note">資料來源：<b>{source_name}</b> · '
        f'{len(data)} 筆 · 金額單位：新台幣仟元 · '
        "損益與現金流量為上半年累計，資產負債表為 6 月 30 日時點</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 上半年關鍵績效")
    kpi_items = [
        ("營業收入", "營收"),
        ("營業毛利", "毛利"),
        ("營業利益", "營業利益"),
        ("本期淨利", "稅後淨利"),
    ]
    columns = st.columns(len(kpi_items))
    for column, (item, title) in zip(columns, kpi_items):
        amounts, _ = get_period_amounts(data, INCOME_REPORT, item, "income")
        current = amounts["2026 上半年"]
        prior = amounts["2025 上半年"]
        growth = (current / prior - 1) * 100 if prior != 0 else None
        delta = (
            f"{growth:+.2f}% 年增"
            if growth is not None
            else "前期為 0，無法計算年增率"
        )
        column.metric(
            label=f"2026 上半年 · {title}",
            value=f"{current:,.0f}",
            delta=delta,
            help=f"2025 上半年：{prior:,.0f} {unit}",
        )
        column.caption(f"2025 同期　{prior:,.0f} {unit}")

    income_comparison, _ = build_comparison_table(
        data, INCOME_REPORT, INCOME_ITEMS, "income"
    )
    balance_comparison, _ = build_comparison_table(
        data, BALANCE_REPORT, BALANCE_ITEMS, "balance"
    )
    cash_flow_comparison, _ = build_comparison_table(
        data, CASH_FLOW_REPORT, CASH_FLOW_ITEMS, "income"
    )
    balance_ratios = ratios.loc[["負債比率", "權益比率"]]

    tab_income, tab_balance, tab_cash_flow, tab_ratios, tab_data = st.tabs(
        ["損益與獲利", "資產負債", "現金流量", "財務比率", "資料檢視"]
    )

    with tab_income:
        st.markdown("#### 營收與獲利金額比較")
        st.caption(f"單位：{unit} · 期間：1 月 1 日至 6 月 30 日")
        st.plotly_chart(amount_figure, use_container_width=True)
        st.markdown("#### 獲利率比較")
        st.plotly_chart(margin_figure, use_container_width=True)
        st.markdown("#### 損益表年度比較")
        income_display = income_comparison.copy()
        income_display["2026 上半年"] = income_display["2026 上半年"].map(
            lambda value: f"{value:,.0f}"
        )
        income_display["2025 上半年"] = income_display["2025 上半年"].map(
            lambda value: f"{value:,.0f}"
        )
        income_display["年增額"] = income_comparison["年增額"].map(
            lambda value: f"{value:+,.0f}"
        )
        income_display["年增率"] = income_comparison["年增率"].map(
            lambda value: f"{value:+.2f}%" if pd.notna(value) else "不適用"
        )
        st.dataframe(income_display, use_container_width=True)

    with tab_balance:
        st.markdown("#### 資產負債結構")
        st.caption(f"單位：{balance_unit} · 比較日期：各年 6 月 30 日")
        st.plotly_chart(balance_figure, use_container_width=True)
        st.markdown("#### 流動資產項目")
        st.caption("僅比較 CSV 中已擷取的現金、應收帳款及存貨。")
        st.plotly_chart(asset_detail_figure, use_container_width=True)

        leverage_figure = make_balance_chart(data)
        st.markdown("#### 負債與權益占總資產比例")
        st.plotly_chart(leverage_figure, use_container_width=True)

        st.markdown("#### 資產負債表年度比較")
        balance_display = balance_comparison.copy()
        for year in analysis.PERIODS:
            balance_display[year] = balance_display[year].map(
                lambda value: f"{value:,.0f}"
            )
        balance_display["年增額"] = balance_comparison["年增額"].map(
            lambda value: f"{value:+,.0f}"
        )
        balance_display["年增率"] = balance_comparison["年增率"].map(
            lambda value: f"{value:+.2f}%" if pd.notna(value) else "不適用"
        )
        st.dataframe(balance_display, use_container_width=True)

    with tab_cash_flow:
        st.markdown("#### 三大活動現金流量")
        st.caption(f"單位：{cash_flow_unit} · 期間：1 月 1 日至 6 月 30 日；負值表示淨流出。")
        st.plotly_chart(cash_flow_figure, use_container_width=True)
        st.markdown("#### 現金流量年度比較")
        cash_flow_display = cash_flow_comparison.copy()
        for year in analysis.PERIODS:
            cash_flow_display[year] = cash_flow_display[year].map(
                lambda value: f"{value:,.0f}"
            )
        cash_flow_display["年增額"] = cash_flow_comparison["年增額"].map(
            lambda value: f"{value:+,.0f}"
        )
        cash_flow_display["年增率"] = cash_flow_comparison["年增率"].map(
            lambda value: f"{value:+.2f}%" if pd.notna(value) else "不適用"
        )
        st.dataframe(cash_flow_display, use_container_width=True)
        st.info("現金流量表僅呈現 CSV 已擷取的營業、投資與籌資活動淨現金流量，不推估未提供的現金流項目。")

    with tab_ratios:
        st.markdown("#### 財務比率年度比較")
        st.plotly_chart(margin_comparison_figure, use_container_width=True)
        ratio_change = pd.DataFrame(
            {
                "2025 上半年": ratios["2025 上半年"],
                "2026 上半年": ratios["2026 上半年"],
                "年變動（百分點）": (
                    ratios["2026 上半年"] - ratios["2025 上半年"]
                ),
            }
        )
        ratio_change.index.name = "財務指標"
        ratio_change = ratio_change.loc[
            ["毛利率", "營業利益率", "稅後淨利率", "負債比率", "權益比率"]
        ]
        st.dataframe(
            ratio_change.style.format(
                {
                    "2025 上半年": "{:.2f}%",
                    "2026 上半年": "{:.2f}%",
                    "年變動（百分點）": "{:+.2f} 個百分點",
                }
            ),
            use_container_width=True,
        )
        st.caption(
            "損益比率以各年度上半年累計金額計算；"
            "負債與權益比率以各年度 6 月 30 日時點金額計算。"
        )

        leverage_change = pd.DataFrame(
            {
                "2025 上半年": balance_ratios["2025 上半年"],
                "2026 上半年": balance_ratios["2026 上半年"],
                "年變動（百分點）": (
                    balance_ratios["2026 上半年"]
                    - balance_ratios["2025 上半年"]
                ),
            }
        )
        leverage_change.index.name = "資本結構指標"
        st.markdown("#### 資本結構")
        st.dataframe(
            leverage_change.style.format(
                {
                    "2025 上半年": "{:.2f}%",
                    "2026 上半年": "{:.2f}%",
                    "年變動（百分點）": "{:+.2f} 個百分點",
                }
            ),
            use_container_width=True,
        )

    with tab_data:
        st.markdown("#### 原始財務資料")
        st.caption("數值與頁碼直接來自目前選用的 CSV；本 Dashboard 不回寫資料。")
        st.dataframe(data, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
