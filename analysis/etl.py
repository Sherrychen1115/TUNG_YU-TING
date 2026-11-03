"""把 data/raw 的三份原始資料整理成 data/clean/annual_2014_2025.csv。

執行方式（在專案根目錄）：
    uv run python analysis/etl.py

只讀取 data/raw，不會修改原始檔。缺值一律留空，不做任何補值。
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pandas as pd
import xlrd
import openpyxl

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "annual_2014_2025.csv"

YEARS = range(2014, 2026)
ROC_OFFSET = 1911  # 民國 103 年 = 西元 2014 年


def roc_to_ad(text: str) -> int:
    """'103年' 或 '103/12/31' 的民國年 → 西元年。"""
    m = re.match(r"\s*(\d{2,3})\s*(年|/)", str(text))
    if not m:
        raise ValueError(f"無法辨識民國年：{text!r}")
    return int(m.group(1)) + ROC_OFFSET


def to_number(text: str) -> float:
    """'9,307.26' → 9307.26"""
    return float(str(text).replace(",", ""))


# ---------------------------------------------------------------------------
# 1. 加權股價指數：每年 12 月最後一個交易日的收盤指數
# ---------------------------------------------------------------------------
def load_taiex() -> pd.Series:
    closes = {}
    for f in sorted(RAW.glob("FMTQIK_*12.csv")):
        file_year = int(f.stem.split("_")[1][:4])
        rows = list(csv.reader(f.read_text(encoding="cp950").splitlines()))

        # 第 1 列是標題（如「103年12月市場成交資訊」），用來確認檔名年份正確
        title_year = roc_to_ad(rows[0][0])
        if title_year != file_year:
            raise ValueError(f"{f.name}：檔名年份 {file_year} 與標題年份 {title_year} 不符")

        header = rows[1]
        col = header.index("發行量加權股價指數")
        # 資料列的日期格式為 民國年/月/日；「說明:」等備註列沒有斜線，會被排除
        data = [r for r in rows[2:] if r and re.fullmatch(r"\d{2,3}/\d{2}/\d{2}", r[0])]

        dates = []
        for r in data:
            y, m, d = (int(x) for x in r[0].split("/"))
            if y + ROC_OFFSET != file_year or m != 12:
                raise ValueError(f"{f.name}：出現非 {file_year} 年 12 月的日期 {r[0]}")
            dates.append((d, to_number(r[col])))

        last_day, close = max(dates)  # 取日期最大的一天，不依賴列的順序
        closes[file_year] = close
        print(f"  {f.name}: {len(data)} 個交易日，最後交易日 12/{last_day:02d}，收盤 {close:,.2f}")

    return pd.Series(closes, name="taiex_close")


# ---------------------------------------------------------------------------
# 2. 經濟成長率（實質 GDP 年增率）
# ---------------------------------------------------------------------------
def load_gdp() -> pd.Series:
    sh = xlrd.open_workbook(RAW / "GDP.xls").sheet_by_index(0)

    # 找出「經濟成長率」所在欄，不寫死欄位位置
    col = next(
        j
        for i in range(sh.nrows)
        for j in range(sh.ncols)
        if str(sh.cell_value(i, j)).strip() == "經濟成長率"
    )

    growth = {}
    for i in range(sh.nrows):
        label = str(sh.cell_value(i, 0)).strip()
        if re.fullmatch(r"\d{2,3}年", label):  # 只取年資料列，排除標題、單位、資料來源列
            value = sh.cell_value(i, col)
            growth[roc_to_ad(label)] = float(value) if value != "" else None

    print(f"  GDP.xls: 經濟成長率在第 {col + 1} 欄，年份 {sorted(growth)}")
    return pd.Series(growth, name="gdp_growth", dtype="float64")


# ---------------------------------------------------------------------------
# 3. 實質經常性薪資（工業及服務業，總計）
# ---------------------------------------------------------------------------
def load_wage() -> pd.DataFrame:
    files = sorted(RAW.glob("薪情平臺匯出資料_*.xlsx"))
    if len(files) != 1:
        raise FileNotFoundError(f"data/raw 應該剛好有 1 個薪情平臺匯出檔，找到 {len(files)} 個")
    # 不用 read_only：此匯出檔缺少 dimension 資訊，唯讀模式會讀不到完整表格
    ws = openpyxl.load_workbook(files[0]).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))

    # 找出「統計值」與「較上年同期增減率」所在的表頭列與欄
    for header in rows:
        if "統計值" in header and "較上年同期增減率" in header:
            c_val = header.index("統計值")
            c_rate = header.index("較上年同期增減率")
            break
    else:
        raise ValueError("找不到「統計值／較上年同期增減率」表頭")

    records = []
    for r in rows:
        year_cell = next((c for c in r if isinstance(c, str) and re.fullmatch(r"\d{2,3}年", c)), None)
        if year_cell is None:
            continue  # 表頭、空白列、註解列
        rate = r[c_rate]
        records.append(
            {
                "year": roc_to_ad(year_cell),
                "real_wage": int(r[c_val]),
                # 官方以「-」表示不比較（108 年行業範圍擴增），保留為缺值
                "real_wage_growth": float(rate) if isinstance(rate, (int, float)) else None,
            }
        )

    df = pd.DataFrame(records).set_index("year")
    print(f"  {files[0].name}: 年份 {df.index.min()}–{df.index.max()}，"
          f"增減率缺值年份 {df.index[df['real_wage_growth'].isna()].tolist()}")
    return df


# ---------------------------------------------------------------------------
def main() -> int:
    print("讀取加權股價指數 ...")
    taiex = load_taiex()
    print("讀取經濟成長率 ...")
    gdp = load_gdp()
    print("讀取實質經常性薪資 ...")
    wage = load_wage()

    df = pd.DataFrame(index=pd.Index(YEARS, name="year"))
    df["taiex_close"] = taiex
    # 年報酬率：只在「前一年」也有年底收盤時計算，避免跨年缺口
    prev = df["taiex_close"].shift(1)
    df["taiex_return"] = ((df["taiex_close"] / prev - 1) * 100).round(2)
    df["gdp_growth"] = gdp
    df["real_wage"] = wage["real_wage"].astype("Int64")
    df["real_wage_growth"] = wage["real_wage_growth"]

    # 檢查：官方薪資增減率應與相鄰年份統計值計算的結果一致（差距 ≤ 0.01 個百分點）
    calc = (df["real_wage"] / df["real_wage"].shift(1) - 1) * 100
    diff = (calc - df["real_wage_growth"]).abs()
    bad = diff[diff > 0.01].dropna()
    if not bad.empty:
        print(f"⚠ 官方薪資增減率與自行計算不一致：{bad.round(3).to_dict()}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(OUT, index=False, encoding="utf-8-sig", na_rep="")
    print(f"\n已輸出 {OUT.relative_to(ROOT)}\n")
    print(df.to_string())

    # 列出缺值，提醒但不中止
    missing = {c: df.index[df[c].isna()].tolist() for c in df.columns if df[c].isna().any()}
    if missing:
        print("\n缺值（保留空白，未補值）：")
        for c, ys in missing.items():
            print(f"  {c}: {ys}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
