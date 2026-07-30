import os
import sys
import json
import logging
import time
import random
import numpy as np
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import akshare as ak
import qlib
from tqdm import tqdm

# ====================== 【稳健型配置】 ======================
MANUAL_START_DATE = None
CHECK_SAMPLE = 200
SKIP_RATE = 0.98
MAX_WORKERS = 1  # 强制单线程，极大地降低被封概率
RETRY_TIMES = 3
BATCH_SIZE = 30  # 每拉取多少只股票进行一次大休息
BATCH_SLEEP = 10  # 大休息的时间（秒）
# ========================================================

PROGRESS_FILE = "update_progress.json"
QLIB_DATA_DIR = Path.home() / ".qlib/qlib_data/cn_data"
INSTRUMENTS_PATH = QLIB_DATA_DIR / "instruments/all.txt"
CALENDAR_PATH = QLIB_DATA_DIR / "calendars/day.txt"

FIELDS_MAP = {
    "open": "开盘", "close": "收盘", "high": "最高", "low": "最低",
    "volume": "成交量", "amount": "成交额", "pct_chg": "涨跌幅", "turnover": "换手率",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger()


def sync_trade_days():
    try:
        df = ak.tool_trade_date_hist_sina()
        days = sorted(df["trade_date"].astype(str).tolist())
        CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CALENDAR_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(days))
        return days
    except:
        return [l.strip() for l in open(CALENDAR_PATH, encoding="utf-8") if len(l.strip()) == 10]


def load_calendar():
    with open(CALENDAR_PATH, encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and len(l.strip()) == 10]
    return lines, {d: i for i, d in enumerate(lines)}


def load_progress():
    if Path(PROGRESS_FILE).exists():
        try:
            return json.load(open(PROGRESS_FILE, encoding="utf-8"))
        except:
            pass
    return {"current_day": None, "done_stocks": []}


def save_progress(day, done_stocks):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump({"current_day": day, "done_stocks": list(done_stocks)}, f)


def has_data(code, target_date, cal_idx):
    try:
        bin_path = QLIB_DATA_DIR / "features" / code.lower() / "close.day.bin"
        if not bin_path.exists(): return False
        arr = np.fromfile(bin_path, dtype="<f")
        s_idx = int(arr[0])
        pos = cal_idx[target_date] - s_idx
        return 0 <= pos < len(arr[1:]) and not np.isnan(arr[pos + 1])
    except:
        return False


def check_day_complete(day, stocks, cal_idx):
    sample = stocks[:CHECK_SAMPLE]
    ok = sum(1 for code in sample if has_data(code, day, cal_idx))
    return ok / len(sample) if sample else 0


def fetch_and_save(code, day, day_idx):
    for i in range(RETRY_TIMES):
        try:
            # 增加随机等待，模拟人类浏览速度
            time.sleep(random.uniform(1.5, 3.0))

            df = ak.stock_zh_a_hist(code, "daily", day.replace("-", ""), day.replace("-", ""), "qfq")
            if df.empty:
                if i == RETRY_TIMES - 1: return False
                time.sleep(5)  # 失败了多等会儿
                continue

            folder = QLIB_DATA_DIR / "features" / code.lower()
            folder.mkdir(exist_ok=True, parents=True)
            for field, col in FIELDS_MAP.items():
                if col not in df.columns: continue
                val = float(df[col].iloc[0])
                bin_path = folder / f"{field}.day.bin"

                if not bin_path.exists():
                    np.array([day_idx, val], dtype="<f").tofile(bin_path)
                else:
                    arr = np.fromfile(bin_path, dtype="<f")
                    s_idx, data = int(arr[0]), arr[1:]
                    pos = day_idx - s_idx
                    if pos < 0: continue

                    if pos >= len(data):
                        new_data = np.full(pos + 1, np.nan, dtype="<f")
                        new_data[:len(data)] = data
                        new_data[pos] = val
                        np.hstack([s_idx, new_data]).tofile(bin_path)
                    else:
                        data[pos] = val
                        np.hstack([s_idx, data]).tofile(bin_path)
            return True
        except:
            if i == RETRY_TIMES - 1: return False
            time.sleep(10)
    return False


def auto_update():
    qlib.init(region="cn")
    all_trade_days = sync_trade_days()
    cal, cal_idx = load_calendar()

    with open(INSTRUMENTS_PATH, encoding="utf-8") as f:
        all_stocks = [line.strip().split("\t")[0] for line in f if line.strip()]

    today = datetime.now().strftime("%Y-%m-%d")
    start_date = MANUAL_START_DATE
    if not start_date:
        log.info("🔍 正在扫描缺失数据...")
        for i in range(len(cal) - 1, -1, -1):
            if cal[i] > today: continue
            if check_day_complete(cal[i], all_stocks, cal_idx) < SKIP_RATE:
                start_date = cal[i]
                break

    todo_days = [d for d in cal if start_date <= d <= today and d in all_trade_days]
    if not todo_days:
        log.info("🎉 数据已是最新。")
        return

    log.info(f"📅 计划更新日期：{todo_days}")

    prog = load_progress()
    for day in todo_days:
        done_stocks = set(prog["done_stocks"]) if prog["current_day"] == day else set()

        # 预检
        if check_day_complete(day, all_stocks, cal_idx) >= SKIP_RATE:
            log.info(f"✅ {day} 完整率已达标，跳过。")
            continue

        stocks_to_fetch = [s for s in all_stocks if s not in done_stocks]
        pbar = tqdm(total=len(all_stocks), desc=f"🚀 {day}", unit="股", initial=len(done_stocks))

        success_count = 0
        batch_counter = 0

        # 虽然用 Executor，但 MAX_WORKERS=1 等同于串行
        with ThreadPoolExecutor(MAX_WORKERS) as executor:
            future_to_stock = {executor.submit(fetch_and_save, s, day, cal_idx[day]): s for s in stocks_to_fetch}

            for future in as_completed(future_to_stock):
                stock = future_to_stock[future]
                if future.result():
                    success_count += 1

                done_stocks.add(stock)
                batch_counter += 1

                # 触发批次长休眠
                if batch_counter >= BATCH_SIZE:
                    time.sleep(BATCH_SLEEP)
                    batch_counter = 0

                save_progress(day, done_stocks)
                pbar.update(1)
                pbar.set_postfix({"成功": success_count, "失败": len(done_stocks) - success_count})

        pbar.close()
        save_progress(None, [])

    if Path(PROGRESS_FILE).exists(): Path(PROGRESS_FILE).unlink()
    log.info("🎊 全部任务完成！")


if __name__ == "__main__":
    auto_update()