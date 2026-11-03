"""用 data/clean/annual_2014_2025.csv 做趨勢圖、標準化指數圖、相關分析與散布圖。

執行方式（在專案根目錄）：
    uv run python analysis/analysis.py

輸出到 analysis/output/。只讀取 data/clean，不會修改任何資料檔。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 不開視窗，直接存檔
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "clean" / "annual_2014_2025.csv"
OUT = ROOT / "analysis" / "output"

START, END = 2015, 2025

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
# 樣式：每個變數固定一個顏色與標記形狀（所有圖一致）
# ---------------------------------------------------------------------------
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"

SERIES = {
    "taiex": {"color": "#2a78d6", "marker": "o", "label": "股價年報酬率"},
    "gdp": {"color": "#eb6834", "marker": "s", "label": "實質 GDP 成長率"},
    "wage": {"color": "#1baf7a", "marker": "^", "label": "實質薪資年增率"},
}


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


def new_fig(w=9.5, h=5.5):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    return fig, ax


def save(fig, name: str, note: str | None = None) -> None:
    if note:
        fig.text(0.01, 0.01, note, fontsize=9, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(OUT / name, facecolor=SURFACE)
    plt.close(fig)
    print(f"  已輸出 {name}")


SOURCE_NOTE = "資料來源：臺灣證券交易所、行政院主計總處（國民所得統計、薪資及生產力統計）"


# ---------------------------------------------------------------------------
# 1. 趨勢圖：三個年增率放同一張
# ---------------------------------------------------------------------------
def plot_trend(df: pd.DataFrame) -> None:
    fig, ax = new_fig()
    cols = {"taiex": "taiex_return", "gdp": "gdp_growth", "wage": "real_wage_growth"}
    years = df.index

    ax.axhline(0, color=AXIS, linewidth=1)
    for key, col in cols.items():
        s = SERIES[key]
        ax.plot(years, df[col], color=s["color"], marker=s["marker"], markersize=7,
                linewidth=2, label=s["label"], markeredgecolor=SURFACE, markeredgewidth=1.5)
        # 線尾直接標示名稱
        last = df[col].dropna()
        ax.annotate(s["label"], (last.index[-1], last.iloc[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK_2)

    # 2019 年薪資缺值說明
    w2018 = df.loc[2018, "real_wage_growth"]
    ax.annotate("2019 年官方未公布\n（統計範圍擴大）", (2019, w2018), xytext=(0, -38),
                textcoords="offset points", ha="center", fontsize=9, color=MUTED)

    style_axes(ax, "股價、經濟成長與實質薪資的年增率（2015–2025）", "年增率（%）")
    ax.set_xticks(list(years))
    ax.set_xlim(START - 0.5, END + 2.3)  # 右側留空間給線尾標籤
    ax.legend(loc="upper left", frameon=False, fontsize=10, ncols=3)
    save(fig, "fig1_trend.png", SOURCE_NOTE + "；股價年報酬率以年底收盤指數計算")


# ---------------------------------------------------------------------------
# 2. 標準化指數圖：2015 = 100
# ---------------------------------------------------------------------------
def plot_index(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DataFrame({
        "taiex_index": df["taiex_close"] / df.loc[START, "taiex_close"] * 100,
        "real_wage_index": df["real_wage"] / df.loc[START, "real_wage"] * 100,
    })

    fig, ax = new_fig()
    ax.axhline(100, color=AXIS, linewidth=1)
    for key, col, label in [("taiex", "taiex_index", "加權指數（年底收盤）"),
                            ("wage", "real_wage_index", "實質經常性薪資")]:
        s = SERIES[key]
        ax.plot(idx.index, idx[col], color=s["color"], marker=s["marker"], markersize=7,
                linewidth=2, label=label, markeredgecolor=SURFACE, markeredgewidth=1.5)
        end = idx[col].iloc[-1]
        ax.annotate(f"{label}\n{end:.1f}", (END, end), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=10, color=INK_2)

    ax.annotate("2019 年起薪資統計範圍擴大", (2019, idx.loc[2019, "real_wage_index"]),
                xytext=(10, 22), textcoords="offset points", ha="left", fontsize=9, color=MUTED,
                arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.8))

    style_axes(ax, "加權指數與實質薪資的累積變化（2015 年 = 100）", "指數（2015 = 100）")
    ax.set_xticks(list(idx.index))
    ax.set_xlim(START - 0.5, END + 2.3)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    save(fig, "fig2_index_2015_100.png", SOURCE_NOTE)
    return idx


# ---------------------------------------------------------------------------
# 3. 相關係數
# ---------------------------------------------------------------------------
PAIRS = [
    ("a", "taiex_return", "gdp_growth", "taiex", "gdp"),
    ("b", "gdp_growth", "real_wage_growth", "gdp", "wage"),
    ("c", "taiex_return", "real_wage_growth", "taiex", "wage"),
]


def correlations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tag, x, y, kx, ky in PAIRS:
        sub = df[[x, y]].dropna()
        excluded = sorted(set(df.index) - set(sub.index))
        r, p = stats.pearsonr(sub[x], sub[y])
        rows.append({
            "pair": tag,
            "x": SERIES[kx]["label"],
            "y": SERIES[ky]["label"],
            "years": f"{sub.index.min()}–{sub.index.max()}",
            "excluded_years": ",".join(map(str, excluded)),
            "n": len(sub),
            "pearson_r": round(r, 3),
            "p_value": round(p, 3),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. 散布圖：每組一張，點旁標年份
# ---------------------------------------------------------------------------
def plot_scatter(df: pd.DataFrame, corr: pd.DataFrame) -> None:
    for (tag, x, y, kx, ky), row in zip(PAIRS, corr.itertuples()):
        sub = df[[x, y]].dropna()
        fig, ax = new_fig(7.5, 6)

        ax.axhline(0, color=AXIS, linewidth=1)
        ax.axvline(0, color=AXIS, linewidth=1)

        # 最小平方法趨勢線（只用來看方向，不代表因果）
        fit = stats.linregress(sub[x], sub[y])
        xs = pd.Series([sub[x].min(), sub[x].max()])
        ax.plot(xs, fit.intercept + fit.slope * xs, color=MUTED, linestyle="--", linewidth=1.2)

        ax.scatter(sub[x], sub[y], s=70, color=SERIES["taiex"]["color"], edgecolors=SURFACE,
                   linewidths=1.5, zorder=3)
        for yr, (vx, vy) in sub.iterrows():
            ax.annotate(str(yr), (vx, vy), xytext=(6, 5), textcoords="offset points",
                        fontsize=9, color=INK_2)

        style_axes(ax, f"({tag}) {SERIES[kx]['label']} vs {SERIES[ky]['label']}",
                   f"{SERIES[ky]['label']}（%）")
        ax.set_xlabel(f"{SERIES[kx]['label']}（%）", color=INK_2, fontsize=11)
        ax.grid(axis="x", color=GRID, linewidth=0.8)

        excl = f"；排除 {row.excluded_years} 年（官方缺值）" if row.excluded_years else ""
        # 統計量放在繪圖區上方，避免蓋住資料點
        ax.set_title(f"({tag}) {SERIES[kx]['label']} vs {SERIES[ky]['label']}",
                     loc="left", fontsize=14, color=INK, pad=30, fontweight="bold")
        ax.text(0, 1.02, f"Pearson r = {row.pearson_r:.2f}，p = {row.p_value:.3f}，n = {row.n}",
                transform=ax.transAxes, va="bottom", fontsize=11, color=INK_2)
        save(fig, f"fig3{tag}_scatter_{x}_vs_{y}.png", f"期間 {row.years}{excl}；虛線為線性趨勢線")


# ---------------------------------------------------------------------------
# 5. 累積變化與年複合成長率（CAGR），基期 2015、終點 2025，共 10 年
# ---------------------------------------------------------------------------
def cumulative(df: pd.DataFrame) -> pd.DataFrame:
    years = END - START  # 10 年

    def row(name, ratio, n_years, method, period=f"{START}–{END}"):
        return {
            "variable": name,
            "period": period,
            "years": n_years,
            "cumulative_change_pct": round((ratio - 1) * 100, 2),
            "cagr_pct": round((ratio ** (1 / n_years) - 1) * 100, 2),
            "method": method,
        }

    taiex_ratio = df.loc[END, "taiex_close"] / df.loc[START, "taiex_close"]
    wage_ratio = df.loc[END, "real_wage"] / df.loc[START, "real_wage"]
    # 實質 GDP：沒有水準值，用 2016–2025 每年成長率連乘，等於 2025 年實質 GDP ÷ 2015 年實質 GDP
    g = df.loc[START + 1:END, "gdp_growth"]
    if g.isna().any():
        raise ValueError("GDP 成長率有缺值，無法連乘")
    gdp_ratio = (1 + g / 100).prod()

    # 補充：2019 年起薪資統計範圍一致的區段
    wage_ratio_1925 = df.loc[END, "real_wage"] / df.loc[2019, "real_wage"]

    return pd.DataFrame([
        row("加權指數（年底收盤，名目）", taiex_ratio, years,
            f"{END} 年底收盤 ÷ {START} 年底收盤"),
        row("實質 GDP", gdp_ratio, years,
            f"∏(1 + 成長率/100)，{START + 1}–{END} 共 {len(g)} 年連乘"),
        row("實質經常性薪資", wage_ratio, years,
            f"{END} 年統計值 ÷ {START} 年統計值（跨 2019 年統計範圍調整）"),
        row("實質經常性薪資（補充）", wage_ratio_1925, END - 2019,
            f"{END} 年統計值 ÷ 2019 年統計值（統計範圍一致）", period=f"2019–{END}"),
    ])


def plot_cumulative(cum: pd.DataFrame) -> None:
    main_rows = cum.iloc[:3]  # 長條圖只畫 2015–2025 三項，補充列只放表格
    keys = ["taiex", "gdp", "wage"]
    labels = ["加權指數\n（年底收盤）", "實質 GDP\n（成長率連乘）", "實質經常性薪資"]

    fig, ax = new_fig(8, 5.5)
    bars = ax.bar(labels, main_rows["cumulative_change_pct"], width=0.55,
                  color=[SERIES[k]["color"] for k in keys], edgecolor=SURFACE, linewidth=2)
    for b, r in zip(bars, main_rows.itertuples()):
        ax.annotate(f"+{r.cumulative_change_pct:.1f}%\n年複合 {r.cagr_pct:.2f}%",
                    (b.get_x() + b.get_width() / 2, b.get_height()), xytext=(0, 6),
                    textcoords="offset points", ha="center", va="bottom", fontsize=11, color=INK)

    style_axes(ax, f"{START}–{END} 年累積變化與年複合成長率", "累積變化（%）")
    ax.axhline(0, color=AXIS, linewidth=1)
    ax.set_ylim(0, main_rows["cumulative_change_pct"].max() * 1.2)
    ax.tick_params(axis="x", colors=INK_2, labelsize=11)
    save(fig, "fig4_cumulative_cagr.png",
         f"基期 {START} 年、共 {END - START} 年；加權指數為名目價格指數（不含股利、未扣通膨），GDP 與薪資為實質值")


# ---------------------------------------------------------------------------
# 6. 領先落後：第 t 年股價報酬 vs 第 t+1 年 GDP 成長率／實質薪資年增率
# ---------------------------------------------------------------------------
def lead_lag(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y_col, ky in [("gdp_growth", "gdp"), ("real_wage_growth", "wage")]:
        for lag in (0, 1):
            pair = pd.DataFrame({
                "x": df["taiex_return"],
                "y": df[y_col].shift(-lag),  # lag=1：把下一年的 y 對齊到今年
            })
            # 只保留 t+lag 也在研究期間內的年份
            pair = pair.loc[START:END - lag]
            missing = pair.index[pair.isna().any(axis=1)].tolist()
            pair = pair.dropna()
            r, p = stats.pearsonr(pair["x"], pair["y"])
            # 穩健性：Spearman 等級相關，以及逐年剔除一年（leave-one-out）後 r 與 p 的範圍
            rho, p_rho = stats.spearmanr(pair["x"], pair["y"])
            loo = [stats.pearsonr(pair.drop(yr)["x"], pair.drop(yr)["y"]) for yr in pair.index]
            loo_r = [v[0] for v in loo]
            loo_p = [v[1] for v in loo]
            rows.append({
                "x": f"股價年報酬率（t）",
                "y": f"{SERIES[ky]['label']}（t+{lag}）" if lag else f"{SERIES[ky]['label']}（t）",
                "lag_years": lag,
                "x_years": f"{pair.index.min()}–{pair.index.max()}",
                "excluded_x_years": ",".join(map(str, missing)),
                "n": len(pair),
                "pearson_r": round(r, 3),
                "p_value": round(p, 3),
                "spearman_rho": round(rho, 3),
                "spearman_p": round(p_rho, 3),
                "loo_r_min": round(min(loo_r), 3),
                "loo_r_max": round(max(loo_r), 3),
                "loo_p_max": round(max(loo_p), 3),
                "loo_p_max_drop_year": pair.index[loo_p.index(max(loo_p))],
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    font = setup_font()
    print(f"中文字型：{font}")

    df = pd.read_csv(DATA, encoding="utf-8-sig").set_index("year")
    df = df.loc[START:END]

    print("繪製圖表 ...")
    plot_trend(df)
    idx = plot_index(df)
    corr = correlations(df)
    plot_scatter(df, corr)

    cum = cumulative(df)
    plot_cumulative(cum)
    lag = lead_lag(df)

    idx.round(1).to_csv(OUT / "index_2015_100.csv", encoding="utf-8-sig")
    corr.to_csv(OUT / "correlations.csv", index=False, encoding="utf-8-sig")
    cum.to_csv(OUT / "cumulative_cagr.csv", index=False, encoding="utf-8-sig")
    lag.to_csv(OUT / "lead_lag.csv", index=False, encoding="utf-8-sig")
    print("  已輸出 index_2015_100.csv、correlations.csv、cumulative_cagr.csv、lead_lag.csv\n")

    print("累積變化與 CAGR：")
    print(cum.to_string(index=False))
    print("\n領先落後：")
    print(lag.to_string(index=False))
    print()

    print("相關係數：")
    print(corr.to_string(index=False))
    print("\n標準化指數（2015 = 100）：")
    print(idx.round(1).to_string())
    print("\n描述統計（2015–2025）：")
    print(df[["taiex_return", "gdp_growth", "real_wage_growth"]].describe().round(2).to_string())


if __name__ == "__main__":
    main()
