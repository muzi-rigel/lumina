"""Qlib 最简单示例：初始化 → 加载数据 → 查看"""
import qlib
from qlib.data import D

# 1. 初始化 Qlib（指定本地数据目录）
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

# 2. 获取贵州茅台(600519)的日线数据
df = D.features(
    instruments=["SH600519"],
    fields=["$close", "$volume", "$high", "$low", "$open"],
    start_time="2026-01-01",
    end_time="2026-04-25",
)

print("贵州茅台 2019~2020 日线数据:")
print(df.head(10))
print(f"\n共 {len(df)} 条记录")
