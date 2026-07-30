import numpy as np
from pathlib import Path

# ==================== 你要验证的日期 ====================
CHECK_DATE = "2026-05-06"
# =======================================================

QLIB_DATA_DIR = Path.home() / ".qlib/qlib_data/cn_data"
CALENDAR_PATH = QLIB_DATA_DIR / "calendars/day.txt"
INSTRUMENTS_PATH = QLIB_DATA_DIR / "instruments/all.txt"

# 加载交易日历，拿到目标日期索引
def get_calendar_index():
    with open(CALENDAR_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    cal_map = {d: i for i, d in enumerate(lines)}
    return lines, cal_map

# 加载所有股票
def get_all_stocks():
    stocks = []
    with open(INSTRUMENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            stock = line.strip().split("\t")[0]
            if stock:
                stocks.append(stock)
    return stocks

# 精准检查：这只股票在【指定日期】到底有没有数据
def has_data(code, target_date, cal_map):
    try:
        bin_file = QLIB_DATA_DIR / "features" / code.lower() / "close.day.bin"
        if not bin_file.exists():
            return False

        arr = np.fromfile(bin_file, dtype="<f")
        start_index = int(arr[0])
        data = arr[1:]

        # 目标位置
        pos = cal_map[target_date] - start_index
        if 0 <= pos < len(data):
            return not np.isnan(data[pos])
        return False
    except:
        return False

# ==================== 主程序 ====================
if __name__ == "__main__":
    print("=" * 60)
    print(f"🔍 精准验证：【{CHECK_DATE}】是否真正有数据")
    print("=" * 60)

    # 加载日历
    cal, cal_map = get_calendar_index()
    if CHECK_DATE not in cal_map:
        print(f"❌ {CHECK_DATE} 不在交易日历中！")
        exit()

    target_idx = cal_map[CHECK_DATE]
    print(f"✅ 交易日历中 {CHECK_DATE} 下标 = {target_idx}")

    # 加载股票
    all_stocks = get_all_stocks()
    total = len(all_stocks)
    print(f"✅ 总股票数：{total}")

    # 抽样验证（超快）
    sample = all_stocks[:500]
    ok_count = 0

    print("\n⏳ 开始验证...")

    for i, code in enumerate(sample):
        if has_data(code, CHECK_DATE, cal_map):
            ok_count += 1

        if i % 100 == 0:
            print(f"进度：{i}/{len(sample)} | 有数据：{ok_count}")

    # 最终报告
    print("\n" + "=" * 60)
    print("📊 【精准验证结果】")
    print("=" * 60)
    print(f"验证日期：{CHECK_DATE}")
    print(f"抽样数量：500 只")
    print(f"✅ 真正有数据：{ok_count} 只")
    print(f"❌ 真正无数据：{500 - ok_count} 只")
    print(f"📈 真实完整率：{ok_count / 500 * 100:.2f}%")

    if ok_count < 10:
        print("\n🚨 结论：几乎没有数据！需要更新！")
    else:
        print("\n✅ 结论：数据正常")