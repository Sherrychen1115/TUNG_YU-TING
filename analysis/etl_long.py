"""把 data/raw 的長年份原始資料整理成 data/clean/annual_long.csv（2001–2025）。

執行方式（在專案根目錄）：
    uv run python analysis/etl_long.py

- 研究期間 2002–2025；2001 年只用來計算 2002 年的報酬與年增率。
- 只讀取 data/raw，不修改原始檔；不覆蓋 annual_2014_2025.csv。
- 缺值一律留空、不補值，原因寫在 note 欄。
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "annual_long.csv"
SHORT = ROOT / "data" / "clean" / "annual_2014_2025.csv"

FIRST, LAST = 2001, 2025  # 2001 為基期年
ROC_OFFSET = 1911  # 民國年 + 1911 = 西元年
WAGE_INDICATOR = "每人每月實質經常性薪資"

DATE_RE = re.compile(r"(\d{2,3})/(\d{2})/(\d{2})")
ROC_YEAR_RE = re.compile(r"(\d{2,3})年")

# 薪資統計範圍調整（依薪情平臺匯出檔的註解）
WAGE_NOTES = {
    2009: "98 年 1 月起薪資統計新增教育業（教育輔助及其他教育業）；官方仍公布年增率",
    2019: "108 年 1 月起薪資統計新增研究發展服務業、學前教育、社會工作服務業，"
          "行業範圍擴大，官方年增率不與前一年比較（原檔為「-」），保留空白",
}


def roc_to_ad(text: str) -> int:
    m = ROC_YEAR_RE.fullmatch(str(text).strip()) or DATE_RE.fullmatch(str(text).strip())
    if not m:
        raise ValueError(f"無法辨識民國年：{text!r}")
    return int(m.group(1)) + ROC_OFFSET


# ---------------------------------------------------------------------------
# 1. 加權股價指數
# ---------------------------------------------------------------------------
def load_taiex() -> tuple[pd.Series, list[str]]:
    issues: list[str] = []
    by_year: dict[int, list[Path]] = defaultdict(list)
    for f in sorted(RAW.glob("FMTQIK_*.csv")):
        m = re.match(r"FMTQIK_(\d{4})12", f.name)
        if m:
            by_year[int(m.group(1))].append(f)

    closes = {}
    for year in range(FIRST, LAST + 1):
        files = by_year.get(year, [])
        if not files:
            issues.append(f"缺 FMTQIK_{year}12.csv")
            continue
        if len(files) > 1:
            digests = {hashlib.md5(f.read_bytes()).hexdigest() for f in files}
            names = "、".join(f.name for f in files)
            if len(digests) > 1:
                raise ValueError(f"{year} 年有多個內容不同的檔案：{names}，請確認要用哪一個")
            files = sorted(files, key=lambda p: len(p.name))  # 優先讀沒有「(1)」的原始檔名
            issues.append(f"{year} 年有內容完全相同的重複檔（{names}），只讀取 {files[0].name}")
        f = files[0]

        rows = list(csv.reader(f.read_text(encoding="cp950").splitlines()))
        if roc_to_ad(rows[0][0].split("年")[0] + "年") != year:
            raise ValueError(f"{f.name}：標題年份與檔名不符：{rows[0][0]}")
        col = rows[1].index("發行量加權股價指數")

        days = []
        for r in rows[2:]:
            # 2001–2010 年檔案的日期前面有空格（如 " 91/12/02"），先去空白再比對
            m = DATE_RE.fullmatch(r[0].strip()) if r else None
            if not m:
                continue  # 「說明」等備註列
            y, mo, d = int(m.group(1)) + ROC_OFFSET, int(m.group(2)), int(m.group(3))
            if y != year or mo != 12:
                raise ValueError(f"{f.name}：出現非 {year} 年 12 月的日期 {r[0]}")
            days.append((d, float(r[col].replace(",", ""))))
        if not days:
            raise ValueError(f"{f.name}：找不到任何每日資料列")

        last_day, close = max(days)
        closes[year] = close
        print(f"  {f.name}: {len(days)} 個交易日，最後交易日 12/{last_day:02d}，收盤 {close:,.2f}")

    return pd.Series(closes, name="taiex_close", dtype="float64"), issues


# ---------------------------------------------------------------------------
# 2. 經濟成長率
# ---------------------------------------------------------------------------
def load_gdp() -> pd.Series:
    sh = xlrd.open_workbook(RAW / "GDP.xls").sheet_by_index(0)
    col = next(j for i in range(sh.nrows) for j in range(sh.ncols)
               if str(sh.cell_value(i, j)).strip() == "經濟成長率")
    growth = {}
    for i in range(sh.nrows):
        label = str(sh.cell_value(i, 0)).strip()
        if ROC_YEAR_RE.fullmatch(label):
            v = sh.cell_value(i, col)
            growth[roc_to_ad(label)] = float(v) if isinstance(v, (int, float)) else None
    s = pd.Series(growth, name="gdp_growth", dtype="float64")
    print(f"  GDP.xls: 經濟成長率在第 {col + 1} 欄，{s.index.min()}–{s.index.max()}，共 {len(s)} 年")
    return s


# ---------------------------------------------------------------------------
# 3. 實質經常性薪資（只取「每人每月實質經常性薪資」這一個指標區塊）
# ---------------------------------------------------------------------------
def load_wage() -> pd.DataFrame:
    files = sorted(RAW.glob("薪情平臺匯出資料_*.xlsx"))
    if len(files) != 1:
        raise FileNotFoundError(f"data/raw 應該剛好有 1 個薪情平臺匯出檔，找到 {len(files)} 個")
    rows = list(openpyxl.load_workbook(files[0]).worksheets[0].iter_rows(values_only=True))

    for header in rows:
        if "統計值" in header and "較上年同期增減率" in header:
            c_val, c_rate = header.index("統計值"), header.index("較上年同期增減率")
            break
    else:
        raise ValueError("找不到「統計值／較上年同期增減率」表頭")

    # 檔案中多個指標上下堆疊；A 欄只在每個區塊第一列寫指標名稱（合併儲存格）
    indicator, records = None, []
    for r in rows:
        if isinstance(r[0], str) and r[0].strip():
            indicator = r[0].strip()
        year_cell = r[1] if len(r) > 1 else None
        if not (indicator and indicator.startswith(WAGE_INDICATOR)
                and isinstance(year_cell, str) and ROC_YEAR_RE.fullmatch(year_cell.strip())):
            continue
        val, rate = r[c_val], r[c_rate]
        records.append({
            "year": roc_to_ad(year_cell),
            "real_wage": int(val) if isinstance(val, (int, float)) else None,
            "real_wage_growth": float(rate) if isinstance(rate, (int, float)) else None,
        })

    df = pd.DataFrame(records).set_index("year")
    if df.index.duplicated().any():
        raise ValueError("實質經常性薪資有重複年份，請檢查匯出檔")
    print(f"  {files[0].name}: {WAGE_INDICATOR} {df.index.min()}–{df.index.max()}，共 {len(df)} 年")
    return df


# ---------------------------------------------------------------------------
def main() -> int:
    print("讀取加權股價指數 ...")
    taiex, issues = load_taiex()
    print("讀取經濟成長率 ...")
    gdp = load_gdp()
    print("讀取實質經常性薪資 ...")
    wage = load_wage()

    df = pd.DataFrame(index=pd.Index(range(FIRST, LAST + 1), name="year"))
    df["taiex_close"] = taiex
    df["taiex_return"] = ((df["taiex_close"] / df["taiex_close"].shift(1) - 1) * 100).round(2)
    df["gdp_growth"] = gdp
    df["real_wage"] = wage["real_wage"].astype("Int64")
    df["real_wage_growth"] = wage["real_wage_growth"]

    # note 欄：逐年記錄缺值原因與統計斷點
    notes: dict[int, list[str]] = defaultdict(list)
    notes[FIRST].append("基期年，只用來計算 2002 年的報酬與年增率")
    for y in df.index:
        if pd.isna(df.loc[y, "taiex_close"]):
            notes[y].append(f"缺 FMTQIK_{y}12.csv，年底收盤與報酬空白")
        elif pd.isna(df.loc[y, "taiex_return"]) and y > FIRST:
            notes[y].append(f"缺 {y - 1} 年底收盤，無法計算報酬")
        if pd.isna(df.loc[y, "gdp_growth"]):
            notes[y].append("GDP.xls 無此年經濟成長率")
        if pd.isna(df.loc[y, "real_wage"]):
            notes[y].append("薪資檔無此年統計值")
    for y, text in WAGE_NOTES.items():
        notes[y].append(text)
    df["note"] = pd.Series({y: "；".join(v) for y, v in notes.items()})

    # 檢查：官方薪資增減率 vs 由統計值自行計算（差距 > 0.01 個百分點就提出）
    calc = (df["real_wage"] / df["real_wage"].shift(1) - 1) * 100
    diff = (calc.astype("float64") - df["real_wage_growth"]).abs()
    bad = diff[diff > 0.01].dropna()
    if not bad.empty:
        print(f"⚠ 官方薪資增減率與自行計算不一致（百分點）：{bad.round(3).to_dict()}")

    # 檢查：2014–2025 年與原本的 annual_2014_2025.csv 是否一致
    if SHORT.exists():
        short = pd.read_csv(SHORT, encoding="utf-8-sig").set_index("year")
        cols = ["taiex_close", "taiex_return", "gdp_growth", "real_wage", "real_wage_growth"]
        a = df.loc[short.index, cols].astype("float64")
        b = short[cols].astype("float64")
        # 只比對舊檔有數值的格子（舊檔缺 2013 年收盤，所以 2014 年報酬在舊檔是空白，屬預期差異）
        same = b.isna() | ((a - b).abs() < 1e-9)
        print("與 annual_2014_2025.csv 重疊年份一致（舊檔有值的欄位全部相同）" if same.all().all()
              else f"⚠ 與 annual_2014_2025.csv 不一致：\n{a[~same.all(axis=1)]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(OUT, index=False, encoding="utf-8-sig", na_rep="")
    print(f"\n已輸出 {OUT.relative_to(ROOT)}")

    if issues:
        print("\n原始檔問題：")
        for i in issues:
            print(f"  - {i}")
    print("\n缺值（保留空白，未補值）：")
    for c in ["taiex_close", "taiex_return", "gdp_growth", "real_wage", "real_wage_growth"]:
        ys = df.index[df[c].isna()].tolist()
        if ys:
            print(f"  {c}: {ys}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
