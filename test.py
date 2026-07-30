import numpy as np
from pathlib import Path

# 配置
CODE = "SH688256"
CHECK_DAY = "2026-05-06"
QLIB_PATH = Path.home() / ".qlib/qlib_data/cn_data"

# 读取交易日历
def get_calendar():
    with open(QLIB_PATH / "calendars" / "day.txt", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]

# 直接读取 bin 价格
def read_real_price():
    cal = get_calendar()
    if CHECK_DAY not in cal:
        print("日期不在日历")
        return

    target_idx = cal.index(CHECK_DAY)

    # 读取 close 价格
    bin_path = QLIB_PATH / "features" / CODE.lower() / "close.day.bin"
    arr = np.fromfile(bin_path, dtype="<f")
    s_idx = int(arr[0])
    data = arr[1:]

    pos = target_idx - s_idx
    if 0 <= pos < len(data):
        price = data[pos]
        print("="*60)
        print(f"✅ 寒武纪 {CODE} {CHECK_DAY} 真实价格（直接读本地bin）")
        print(f"💰 收盘价 = {price:.2f}")
        print("="*60)
    else:
        print("❌ 无数据")

if __name__ == "__main__":
    read_real_price()