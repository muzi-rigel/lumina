"""重试下载之前失败的股票，追加到现有Qlib数据集"""
import time, logging
from pathlib import Path
import numpy as np
import pandas as pd
import akshare as ak

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("retry")

QLIB_DIR = Path.home() / ".qlib/qlib_data/cn_data"
START = "20200101"
END = "20260505"
MAX_RETRIES = 5
SLEEP = 0.5

FIELDS_MAP = {"open": "开盘", "close": "收盘", "high": "最高", "low": "最低",
              "volume": "成交量", "amount": "成交额", "pct_chg": "涨跌幅", "turnover": "换手率"}

# 加载现有日历
cal_path = QLIB_DIR / "calendars" / "day.txt"
with open(cal_path) as f:
    calendar = [l.strip() for l in f if l.strip()]
date_to_idx = {d: i for i, d in enumerate(calendar)}
log.info("已加载 %d 个交易日", len(calendar))

# 获取缺失列表
existing = set(d.name.upper() for d in (QLIB_DIR / "features").iterdir() if d.is_dir())
all_stocks = set(ak.stock_zh_a_spot_em()["代码"].tolist())
missing = sorted(all_stocks - existing)
log.info("缺失 %d 只，开始下载", len(missing))

success, failed = 0, []
for i, code in enumerate(missing):
    df = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=START, end_date=END, adjust="qfq")
            if df is not None and not df.empty:
                break
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(2)

    if df is None or df.empty:
        failed.append(code)
        if i % 10 == 0:
            log.info("进度: %d/%d (成功 %d, 失败 %d)", i, len(missing), success, len(failed))
        time.sleep(SLEEP)
        continue

    try:
        df["日期"] = pd.to_datetime(df["日期"])
        df_dates = df["日期"].dt.strftime("%Y-%m-%d")
        indices = [date_to_idx[d] for d in df_dates if d in date_to_idx]
        if not indices:
            failed.append(code)
            time.sleep(SLEEP)
            continue

        stock_dir = QLIB_DIR / "features" / code.lower()
        stock_dir.mkdir(parents=True, exist_ok=True)
        start_idx = indices[0]

        for f_en, f_cn in FIELDS_MAP.items():
            if f_cn not in df.columns:
                continue
            vals = [float(df[f_cn].values[j]) for j, d in enumerate(df_dates) if d in date_to_idx]
            if not vals:
                continue
            with open(stock_dir / f"{f_en}.day.bin", "wb") as fp:
                np.hstack([start_idx, vals]).astype("<f").tofile(fp)

        # 追加 instrument 行
        inst_line = f"{code.upper()}\t{calendar[indices[0]]}\t{calendar[indices[-1]]}"
        with open(QLIB_DIR / "instruments" / "all.txt", "a") as f:
            f.write("\n" + inst_line)

        success += 1
    except Exception as e:
        log.warning("%s 写入失败: %s", code, e)
        failed.append(code)

    if i % 20 == 0:
        log.info("进度: %d/%d (成功 %d)", i, len(missing), success)
    time.sleep(SLEEP)

log.info("重试完成: 成功 %d, 仍失败 %d", success, len(failed))
if failed:
    log.info("失败列表: %s", ",".join(failed))
