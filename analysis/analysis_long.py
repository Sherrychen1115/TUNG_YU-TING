"""用 data/clean/annual_long.csv 做 2002–2025 年的長期分析。

執行方式（在專案根目錄）：
    uv run python analysis/analysis_long.py

- 研究期間 2002–2025；2001 年是基期，不納入任何相關或統計。
- 輸出到 analysis/output_long/，不覆蓋 analysis/output/。
- 只讀取 data/clean/annual_long.csv，不修改任何資料檔。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 不開視窗，直接存檔
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "clean" / "annual_long.csv"
OUT = ROOT / "analysis" / "output_long"

START, END = 2002, 2025
CRISIS = {"2008–2009 金融海嘯": [2008, 2009], "2020 疫情": [2020]}
WAGE_BREAKS = {2009: "2009 新增教育業", 2019: "2019 新增研發服務、\n學前教育、社工服務業"}

# ---------------------------------------------------------------------------
# 中文字型：優先用 Windows 內建微軟正黑體，找不到再依序嘗試其他常見中文字型
# ---------------------------------------------------------------------------
FONT_FILES = [
    Path("C:/Windows/Fonts/msjh.ttc"),
    Path("C:/Windows/Fonts/msjh.ttf"),
    Path("C:/Windows/Fonts/mingliu.ttc"),
]
FONT_NAMES = ["Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC", "Noto Sans TC", "MingLiU"]


def setup_font() -> str:
    for f in FONT_FILES:
        if f.exists():
            font_manager.fontManager.addfont(str(f))
            name = font_manager.FontProperties(fname=str(f)).get_name()
            break
    else:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        name = next((n for n in FONT_NAMES if n in installed), None)
        if name is None:
            raise RuntimeError("找不到中文字型，圖中的中文會變成方框。請安裝微軟正黑體或 Noto Sans TC。")
    plt.rcParams["font.family"] = [name]
    plt.rcParams["axes.unicode_minus"] = False  # 負號用 ASCII，避免某些字型的負號變方框
    return name


# ---------------------------------------------------------------------------
# 樣式（與 analysis.py 相同）
# ---------------------------------------------------------------------------
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
SHADE = "#efeee8"

SERIES = {
    "taiex": {"color": "#2a78d6", "marker": "o", "label": "股價年報酬率"},
    "gdp": {"color": "#eb6834", "marker": "s", "label": "實質 GDP 成長率"},
    "wage": {"color": "#1baf7a", "marker": "^", "label": "實質薪資年增率"},
}
SOURCE_NOTE = "資料來源：臺灣證券交易所、行政院主計總處（國民所得統計、薪資及生產力統計）"


def style_axes(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=14, color=INK, pad=12, fontweight="bold")
    ax.set_ylabel(ylabel, color=INK_2, fontsize=11)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=10)


def save(fig, name: str, note: str | None = None) -> None:
    if note:
        fig.text(0.01, 0.01, note, fontsize=9, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(OUT / name, facecolor=SURFACE)
    plt.close(fig)
    print(f"  已輸出 {name}")


def shade_crises(ax, label_y: float | None = None) -> None:
    """2008–2009 與 2020 以灰底標示；label_y 給定時在頂端寫上名稱（軸座標）。"""
    for name, yrs in CRISIS.items():
        ax.axvspan(min(yrs) - 0.5, max(yrs) + 0.5, color=SHADE, zorder=0)
        if label_y is not None:
            ax.text((min(yrs) + max(yrs)) / 2, label_y, name, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=9, color=INK_2)


# ---------------------------------------------------------------------------
# 1. 趨勢圖：三個年增率
# ---------------------------------------------------------------------------
def plot_trend(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    shade_crises(ax, label_y=0.99)
    ax.axhline(0, color=AXIS, linewidth=1)

    cols = {"taiex": "taiex_return", "gdp": "gdp_growth", "wage": "real_wage_growth"}
    for key, col in cols.items():
        s = SERIES[key]
        ax.plot(df.index, df[col], color=s["color"], marker=s["marker"], markersize=6,
                linewidth=2, label=s["label"], markeredgecolor=SURFACE, markeredgewidth=1.2)
        last = df[col].dropna()
        ax.annotate(s["label"], (last.index[-1], last.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK_2)

    ax.annotate("2019 年薪資年增率\n官方未公布（範圍擴大）", (2019, 0), xytext=(0, -55),
                textcoords="offset points", ha="center", fontsize=9, color=MUTED,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.8))

    style_axes(ax, f"股價、經濟成長與實質薪資的年增率（{START}–{END}）", "年增率（%）")
    ax.set_xticks(list(range(START, END + 1, 1)))
    ax.tick_params(axis="x", labelrotation=45)
    ax.set_xlim(START - 0.6, END + 2.8)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.93), frameon=False, fontsize=10, ncols=3)
    save(fig, "fig1_trend.png",
         SOURCE_NOTE + "；灰底為 2008–2009、2020；股價報酬為名目、不含股利")


# ---------------------------------------------------------------------------
# 2. 標準化指數圖：2002 = 100（上：兩者同軸；下：薪資放大並標註統計範圍調整）
# ---------------------------------------------------------------------------
def index_2002(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "taiex_index": df["taiex_close"] / df.loc[START, "taiex_close"] * 100,
        "real_wage_index": df["real_wage"].astype("float64") / df.loc[START, "real_wage"] * 100,
    })


def plot_index(idx: pd.DataFrame) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9), dpi=150, sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    fig.patch.set_facecolor(SURFACE)

    lines = [("taiex", "taiex_index", "加權指數（年底收盤，名目）"),
             ("wage", "real_wage_index", "實質經常性薪資")]
    ax1.axhline(100, color=AXIS, linewidth=1)
    for key, col, label in lines:
        s = SERIES[key]
        ax1.plot(idx.index, idx[col], color=s["color"], marker=s["marker"], markersize=6,
                 linewidth=2, label=label, markeredgecolor=SURFACE, markeredgewidth=1.2)
        end = idx[col].iloc[-1]
        ax1.annotate(f"{label}\n{end:.1f}", (END, end), xytext=(8, 0),
                     textcoords="offset points", va="center", fontsize=10, color=INK_2)
    style_axes(ax1, f"加權指數與實質薪資的累積變化（{START} 年 = 100）", f"指數（{START} = 100）")
    ax1.legend(loc="upper left", frameon=False, fontsize=10)

    # 下圖：薪資放大
    s = SERIES["wage"]
    ax2.axhline(100, color=AXIS, linewidth=1)
    ax2.plot(idx.index, idx["real_wage_index"], color=s["color"], marker=s["marker"],
             markersize=6, linewidth=2, markeredgecolor=SURFACE, markeredgewidth=1.2)
    for yr, text in WAGE_BREAKS.items():
        ax2.axvline(yr - 0.5, color=MUTED, linestyle="--", linewidth=1)
        ax2.text(yr - 0.4, 0.97, f"統計範圍調整：{text}", transform=ax2.get_xaxis_transform(),
                 ha="left", va="top", fontsize=9, color=INK_2)
    ax1.axvline(2009 - 0.5, color=MUTED, linestyle="--", linewidth=0.8)
    ax1.axvline(2019 - 0.5, color=MUTED, linestyle="--", linewidth=0.8)
    style_axes(ax2, "實質經常性薪資（放大）", f"指數（{START} = 100）")
    lo, hi = idx["real_wage_index"].min(), idx["real_wage_index"].max()
    ax2.set_ylim(lo - 1.5, hi + 3.5)

    ax2.set_xticks(list(range(START, END + 1)))
    ax2.tick_params(axis="x", labelrotation=45)
    ax2.set_xlim(START - 0.6, END + 3.2)
    save(fig, "fig2_index_2002_100.png",
         SOURCE_NOTE + "；虛線為薪資統計範圍調整（2009、2019）；加權指數不含股利")


# ---------------------------------------------------------------------------
# 3. 相關分析
# ---------------------------------------------------------------------------
# (標籤, x 欄, y 欄, y 是否取下一年, 是否為探索性)
PAIRS = [
    ("a", "taiex_return", "gdp_growth", 0, False),
    ("b", "gdp_growth", "real_wage_growth", 0, False),
    ("c", "taiex_return", "real_wage_growth", 0, False),
    ("d1", "taiex_return", "gdp_growth", 1, True),
    ("d2", "taiex_return", "real_wage_growth", 1, True),
]
LABEL = {"taiex_return": "股價年報酬率", "gdp_growth": "實質 GDP 成長率",
         "real_wage_growth": "實質薪資年增率"}

SAMPLES = {
    "全樣本": [],
    "排除 2008–2009": [2008, 2009],
    "排除 2020": [2020],
    "排除 2008、2009、2020": [2008, 2009, 2020],
}


def pair_frame(df: pd.DataFrame, x: str, y: str, lag: int) -> pd.DataFrame:
    """x 取第 t 年、y 取第 t+lag 年；t 與 t+lag 都必須在研究期間內。"""
    p = pd.DataFrame({"x": df[x], "y": df[y].shift(-lag)}).loc[START:END - lag]
    p["y_year"] = p.index + lag
    return p


def holm(pvals: list[float]) -> list[float]:
    """Holm–Bonferroni 校正後的 p 值。"""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj.tolist()


def correlations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tag, x, y, lag, explor in PAIRS:
        base = pair_frame(df, x, y, lag)
        missing = base.index[base[["x", "y"]].isna().any(axis=1)].tolist()
        for sname, drop in SAMPLES.items():
            # 第 t 年或第 t+lag 年落在排除年份，該組觀察值就拿掉
            keep = ~base.index.isin(drop) & ~base["y_year"].isin(drop)
            dropped = base.index[~keep].tolist()
            sub = base[keep].dropna()
            r, p = stats.pearsonr(sub["x"], sub["y"])
            rho, p_rho = stats.spearmanr(sub["x"], sub["y"])
            y_label = LABEL[y] + ("（下一年）" if lag else "")
            rows.append({
                "pair": tag,
                "x": LABEL[x],
                "y": y_label,
                "exploratory": "是" if explor else "否",
                "sample": sname,
                "x_years": f"{sub.index.min()}–{sub.index.max()}",
                "missing_x_years": ",".join(map(str, missing)),
                "dropped_x_years": ",".join(map(str, dropped)),
                "n": len(sub),
                "pearson_r": round(r, 3),
                "pearson_p": round(p, 6),
                "spearman_rho": round(rho, 3),
                "spearman_p": round(p_rho, 6),
            })
    out = pd.DataFrame(rows)
    # 多重比較：(1) 主表 5 組全樣本 Pearson 之間；(2) 全部 20 個 Pearson 檢定之間
    main = out["sample"] == "全樣本"
    out.loc[main, "pearson_p_holm_main5"] = [round(v, 6) for v in holm(out.loc[main, "pearson_p"])]
    out["pearson_p_holm_all20"] = [round(v, 6) for v in holm(out["pearson_p"])]
    return out


def plot_scatter(df: pd.DataFrame, corr: pd.DataFrame) -> None:
    """五組相關的散布圖（小倍數）；2008、2009、2020 用不同顏色標出。"""
    fig, axes = plt.subplots(2, 3, figsize=(15, 9.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    hi = {2008, 2009, 2020}
    for ax, (tag, x, y, lag, explor) in zip(axes.flat, PAIRS):
        sub = pair_frame(df, x, y, lag).dropna()
        row = corr[(corr["pair"] == tag) & (corr["sample"] == "全樣本")].iloc[0]
        ax.axhline(0, color=AXIS, linewidth=1)
        ax.axvline(0, color=AXIS, linewidth=1)
        fit = stats.linregress(sub["x"], sub["y"])
        xs = np.array([sub["x"].min(), sub["x"].max()])
        ax.plot(xs, fit.intercept + fit.slope * xs, color=MUTED, linestyle="--", linewidth=1.1)
        mark = sub.index.isin(hi) | sub["y_year"].isin(hi)
        ax.scatter(sub.loc[~mark, "x"], sub.loc[~mark, "y"], s=45, color=SERIES["taiex"]["color"],
                   edgecolors=SURFACE, linewidths=1.2, zorder=3)
        ax.scatter(sub.loc[mark, "x"], sub.loc[mark, "y"], s=55, color=SERIES["gdp"]["color"],
                   edgecolors=SURFACE, linewidths=1.2, zorder=4, marker="D")
        for yr, r in sub.iterrows():
            lbl = str(yr) if not lag else f"{yr}→{int(r['y_year'])}"
            ax.annotate(lbl, (r["x"], r["y"]), xytext=(4, 4), textcoords="offset points",
                        fontsize=7.5, color=INK_2)
        title = f"({tag}) {row['x']}\nvs {row['y']}" + ("〔探索性〕" if explor else "")
        style_axes(ax, title, f"{row['y']}（%）")
        ax.set_title(title, loc="left", fontsize=11.5, color=INK, pad=20, fontweight="bold")
        ax.set_xlabel(f"{row['x']}（%）", color=INK_2, fontsize=10)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        p_txt = "p < 0.001" if row["pearson_p"] < 0.001 else f"p = {row['pearson_p']:.3f}"
        ax.text(0, 1.01, f"r = {row['pearson_r']:.2f}，{p_txt}，n = {row['n']}（未校正）",
                transform=ax.transAxes, va="bottom", fontsize=9.5, color=INK_2)
    # 第 6 格放圖例說明
    leg = axes.flat[5]
    leg.axis("off")
    leg.scatter([], [], s=45, color=SERIES["taiex"]["color"], label="一般年份")
    leg.scatter([], [], s=55, color=SERIES["gdp"]["color"], marker="D",
                label="涉及 2008、2009 或 2020 的年份")
    leg.plot([], [], color=MUTED, linestyle="--", label="線性趨勢線（只看方向）")
    leg.legend(loc="center left", frameon=False, fontsize=11)
    leg.text(0.02, 0.2, "d1、d2 的點標示為「股價年份→下一年」\n相關不等於因果；p 值未做多重比較校正",
             transform=leg.transAxes, fontsize=10, color=INK_2, va="top")
    save(fig, "fig3_scatter.png", SOURCE_NOTE + f"；全樣本，研究期間 {START}–{END}")


# ---------------------------------------------------------------------------
# 4. 累積變化與年複合成長率
# ---------------------------------------------------------------------------
def gdp_ratio(df: pd.DataFrame, a: int, b: int) -> float:
    """第 b 年實質 GDP ÷ 第 a 年實質 GDP = (a+1)…b 年成長率連乘。"""
    g = df.loc[a + 1:b, "gdp_growth"]
    if g.isna().any() or len(g) != b - a:
        raise ValueError(f"{a + 1}–{b} 年 GDP 成長率有缺值，無法連乘")
    return float((1 + g / 100).prod())


def cumulative(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def add(var, a, b, ratio, method):
        n = b - a
        rows.append({
            "variable": var,
            "period": f"{a}–{b}",
            "years": n,
            "start_value": None,
            "cumulative_change_pct": round((ratio - 1) * 100, 2),
            "cagr_pct": round((ratio ** (1 / n) - 1) * 100, 2),
            "method": method,
        })

    def taiex(a, b):
        add("加權指數（年底收盤，名目、不含股利）", a, b,
            df.loc[b, "taiex_close"] / df.loc[a, "taiex_close"], f"{b} 年底收盤 ÷ {a} 年底收盤")

    def gdp(a, b):
        add("實質 GDP", a, b, gdp_ratio(df, a, b), f"{a + 1}–{b} 年成長率連乘")

    def wage(a, b, note=""):
        add("實質經常性薪資", a, b, df.loc[b, "real_wage"] / df.loc[a, "real_wage"],
            f"{b} 年統計值 ÷ {a} 年統計值{note}")

    # 主表：2002–2025
    taiex(START, END)
    gdp(START, END)
    wage(START, END, "（跨 2009、2019 兩次統計範圍調整）")

    # 薪資斷點前後：統計範圍一致的三段，以及跨斷點的兩年
    for a, b, note in [(2002, 2008, "（調整前，範圍一致）"),
                       (2008, 2009, "（跨 2009 調整，前後範圍不同）"),
                       (2009, 2018, "（兩次調整之間，範圍一致）"),
                       (2018, 2019, "（跨 2019 調整，前後範圍不同）"),
                       (2019, END, "（2019 調整後，範圍一致）")]:
        wage(a, b, note)
    # 同樣三段的股價與 GDP，方便對照
    for a, b in [(2002, 2008), (2009, 2018), (2019, END)]:
        taiex(a, b)
        gdp(a, b)

    out = pd.DataFrame(rows).drop(columns="start_value")
    out.insert(0, "table", ["主表"] * 3 + ["薪資斷點"] * 5 + ["分段對照"] * 6)
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    font = setup_font()
    print(f"中文字型：{font}")

    df = pd.read_csv(DATA, encoding="utf-8-sig").set_index("year").loc[START:END]
    if df.index.min() != START or df.index.max() != END or len(df) != END - START + 1:
        raise ValueError("annual_long.csv 年份不完整")

    print("繪製圖表 ...")
    plot_trend(df)
    idx = index_2002(df)
    plot_index(idx)
    corr = correlations(df)
    plot_scatter(df, corr)
    cum = cumulative(df)

    main_tbl = corr[corr["sample"] == "全樣本"].drop(columns=["sample", "pearson_p_holm_all20"])
    robust = corr.drop(columns=["pearson_p_holm_main5"])
    idx.round(1).to_csv(OUT / "index_2002_100.csv", encoding="utf-8-sig")
    main_tbl.to_csv(OUT / "correlations.csv", index=False, encoding="utf-8-sig")
    robust.to_csv(OUT / "robustness.csv", index=False, encoding="utf-8-sig")
    cum.to_csv(OUT / "cumulative_cagr.csv", index=False, encoding="utf-8-sig")
    print("  已輸出 index_2002_100.csv、correlations.csv、robustness.csv、cumulative_cagr.csv\n")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print("相關係數（全樣本）：")
    print(main_tbl.to_string(index=False))
    print("\n穩健性檢查：")
    print(robust[["pair", "sample", "x_years", "n", "pearson_r", "pearson_p", "spearman_rho",
                  "spearman_p", "pearson_p_holm_all20"]].to_string(index=False))
    print("\n累積變化與 CAGR：")
    print(cum.to_string(index=False))
    print(f"\n標準化指數（{START} = 100）：")
    print(idx.round(1).to_string())
    print(f"\n描述統計（{START}–{END}）：")
    desc = df[["taiex_return", "gdp_growth", "real_wage_growth"]].describe().round(2)
    print(desc.to_string())
    for c in ["taiex_return", "gdp_growth", "real_wage_growth"]:
        s = df[c].dropna()
        print(f"  {c}: 最低 {s.min():.2f}（{s.idxmin()}）、最高 {s.max():.2f}（{s.idxmax()}）、"
              f"負值年數 {int((s < 0).sum())}：{s[s < 0].index.tolist()}")


if __name__ == "__main__":
    main()
