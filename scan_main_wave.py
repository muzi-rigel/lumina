import qlib
from qlib.data import D
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    bar = (dif - dea) * 2
    return dif, dea, bar


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    # 防止除以0报错
    avg_loss = avg_loss.replace(0, np.nan)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def main():
    # 初始化Qlib
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

    # 自动获取最新数据日期
    latest_info = D.features(D.instruments("all"), ["$close"]).index.max()
    latest_date = latest_info[1] if isinstance(latest_info, tuple) else latest_info
    print(f"📊 数据最新日期：{latest_date.strftime('%Y-%m-%d')}")

    # 时间范围：从6年前到最新日期
    start_time = (latest_date - timedelta(days=365*6)).strftime("%Y-%m-%d")
    end_time = latest_date.strftime("%Y-%m-%d")

    # 获取基础行情数据
    instruments = D.instruments(market="all")
    fields = ["$open", "$close", "$high", "$low", "$volume"]
    df = D.features(instruments, fields, start_time, end_time)

    # 整理索引
    df = df.reset_index()
    df.rename(columns={"instrument": "code", "datetime": "date"}, inplace=True)

    # 计算均线
    df["ma5"] = df["$close"].rolling(5).mean()
    df["ma10"] = df["$close"].rolling(10).mean()
    df["ma20"] = df["$close"].rolling(20).mean()
    df["ma60"] = df["$close"].rolling(60).mean()

    # 计算量能指标
    df["vol5"] = df["$volume"].rolling(5).mean()
    df["vol20"] = df["$volume"].rolling(20).mean()

    # 计算MACD和RSI
    df["dif"], df["dea"], df["macd_bar"] = calc_macd(df["$close"])
    df["rsi14"] = calc_rsi(df["$close"], 14)

    # 主升浪前期 四重共振条件
    cond = (
        # 1. 均线多头排列
        (df["ma5"] > df["ma10"]) &
        (df["ma10"] > df["ma20"]) &
        (df["ma20"] > df["ma60"]) &
        # 股价站上中长期均线
        (df["$close"] > df["ma20"]) &
        (df["$close"] > df["ma60"]) &
        # 2. 量能：缩量洗盘 + 温和放量启动
        (df["vol5"] < df["vol20"] * 0.6) &
        (df["$volume"] > df["vol5"] * 1.4) &
        # 3. MACD：零轴上方、金叉、红柱放大（强势空中加油）
        (df["dif"] > 0) &
        (df["dif"] > df["dea"]) &
        # 4. RSI：强势区间，不超买
        (df["rsi14"] > 50) &
        (df["rsi14"] < 70)
    )

    # 筛选最新一天的候选股票
    candidates = df[df["date"] == latest_date][cond].copy()

    print("\n" + "=" * 120)
    print(f"📈 主升浪前期 · 四重共振选股【{latest_date.strftime('%Y-%m-%d')}】")
    print("=" * 120)

    # 输出关键信息（带股票代码）
    show_cols = [
        "code", "$close", "ma5", "ma20", "ma60",
        "dif", "dea", "rsi14", "$volume"
    ]
    print(candidates[show_cols].to_string(index=False))

    print(f"\n✅ 今日筛选出主升浪前期标的数量：{len(candidates)} 只")


if __name__ == "__main__":
    main()