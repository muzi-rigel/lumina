"""
Qlib 数据完整性校验（真正全量股票版）
"""
import qlib
from qlib.data import D
import pandas as pd
from pathlib import Path

# ======================【你只需要改这里】======================
START_DATE = "2026-04-27"
END_DATE   = "2026-04-27"
# ==============================================================

def get_all_stocks():
    """
    从 Qlib 目录读取真正的全部股票列表
    """
    inst_file = Path.home() / ".qlib/qlib_data/cn_data/instruments/all.txt"
    stocks = []
    with open(inst_file, "r", encoding="utf-8") as f:
        for line in f:
            code = line.strip().split("\t")[0]
            if code:
                stocks.append(code)
    return stocks

def check_integrity(start_date, end_date):
    print("=" * 60)
    print("📊 Qlib 数据完整性校验（全量股票）")
    print(f"📅 检查区间：{start_date} -> {end_date}")
    print("=" * 60)

    qlib.init(region="cn")

    # 交易日历
    calendar = D.calendar(start_time=start_date, end_time=end_date)
    calendar = [d.strftime("%Y-%m-%d") for d in calendar]
    required_days = len(calendar)
    print(f"✅ 应存在交易日：{required_days} 天")
    print(f"✅ 日期列表：{calendar}")
    print("-" * 60)

    # 🔥 修复：读取全部股票
    all_stocks = get_all_stocks()
    total_count = len(all_stocks)
    print(f"✅ 总股票数量：{total_count} 只")
    print("-" * 60)

    ok_stocks = []
    bad_stocks = []
    progress = 0

    for code in all_stocks:
        progress += 1
        try:
            df = D.features([code], ["$close"], start_time=start_date, end_time=end_date)
            existing_days = len(df.dropna())

            if existing_days >= required_days - 1:
                ok_stocks.append(code)
            else:
                bad_stocks.append(f"{code} | 缺失{required_days-existing_days}天")
        except:
            bad_stocks.append(f"{code} | 读取失败")

        if progress % 200 == 0:
            pct = progress / total_count * 100
            print(f"进度：{progress}/{total_count} ({pct:.1f}%) ✅{len(ok_stocks)} ❌{len(bad_stocks)}")

    print("\n" + "=" * 60)
    print("🎉 校验完成")
    print("=" * 60)
    print(f"区间：{start_date} ~ {end_date}")
    print(f"应存在天数：{required_days}")
    print(f"总股票：{total_count}")
    print(f"✅ 完整：{len(ok_stocks)}")
    print(f"❌ 缺失：{len(bad_stocks)}")
    print(f"📈 完整率：{len(ok_stocks)/total_count*100:.2f}%")

    if bad_stocks:
        with open("bad_stocks.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(bad_stocks))
        print(f"\n📄 缺失列表：bad_stocks.txt")

    return ok_stocks, bad_stocks

if __name__ == "__main__":
    check_integrity(START_DATE, END_DATE)