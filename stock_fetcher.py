"""
A股全量实时股票数据获取并存储到MySQL数据库
功能:
1. 获取全量A股实时行情数据（不筛选）
2. 自动创建数据库和表
3. 交易时间高频轮询，非交易时间低频轮询
4. 批量写入 + 断线重连
"""

import os
import time
import logging
from datetime import datetime, time as dt_time
from pathlib import Path

import akshare as ak
import pandas as pd
import pymysql
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 环境变量（db_config 已加载，此处确保本文件直接运行时也能加载）
# ---------------------------------------------------------------------------
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'stock_data'),
    'charset': os.environ.get('DB_CHARSET', 'utf8mb4'),
}

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('stock_fetcher')

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
TRADING_START_MORNING = dt_time(9, 30)
TRADING_END_MORNING   = dt_time(11, 30)
TRADING_START_AFTER   = dt_time(13, 0)
TRADING_END_AFTER     = dt_time(15, 0)

POLL_INTERVAL_TRADING     = int(os.environ.get('POLL_INTERVAL_TRADING', 5))
POLL_INTERVAL_NON_TRADING = int(os.environ.get('POLL_INTERVAL_NON_TRADING', 60))
MAX_RETRIES               = 3

# akshare 列名 → 数据库列名 映射
COLUMN_MAP = {
    '代码':        'stock_code',
    '名称':        'stock_name',
    '最新价':      'price',
    '涨跌幅':      'change_percent',
    '涨跌额':      'change_amount',
    '成交量':      'volume',
    '成交额':      'amount',
    '今开':        'open_price',
    '最高':        'high_price',
    '最低':        'low_price',
    '昨收':        'pre_close',
    '换手率':      'turnover_rate',
    '市盈率-动态': 'pe_ratio',
    '市净率':      'pb_ratio',
    '总市值':      'total_mv',
    '流通市值':    'circ_mv',
    '量比':        'volume_ratio',
    '振幅':        'amplitude',
}

INSERT_COLUMNS = list(COLUMN_MAP.values()) + ['record_time']
INSERT_SQL = (
    "INSERT INTO stock_realtime ("
    + ", ".join(INSERT_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(INSERT_COLUMNS))
    + ")"
)


# ---------------------------------------------------------------------------
class StockDataFetcher:
    def __init__(self):
        self.db_config = DB_CONFIG.copy()
        self.conn = None

    # ---- 数据库初始化 ----

    def create_database_and_tables(self):
        """创建数据库和表（如不存在）"""
        db = self.db_config['database']
        try:
            # 先连接到 MySQL 服务（不指定库）
            conn = pymysql.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                charset=self.db_config['charset'],
            )
            with conn.cursor() as cur:
                cur.execute(
                    "CREATE DATABASE IF NOT EXISTS `%s` "
                    "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci" % db
                )
            conn.close()
            log.info("数据库 %s 就绪", db)
        except Exception as e:
            log.error("创建数据库失败: %s", e)
            raise

        # 连接到目标库
        self.conn = pymysql.connect(**self.db_config)
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS stock_realtime (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        stock_code    VARCHAR(10)   NOT NULL COMMENT '股票代码',
                        stock_name    VARCHAR(50)   NOT NULL COMMENT '股票名称',
                        price         DECIMAL(10,2)          COMMENT '最新价',
                        change_percent DECIMAL(10,2)         COMMENT '涨跌幅%',
                        change_amount DECIMAL(10,2)          COMMENT '涨跌额',
                        volume        BIGINT                 COMMENT '成交量',
                        amount        DECIMAL(18,2)          COMMENT '成交额',
                        open_price    DECIMAL(10,2)          COMMENT '开盘价',
                        high_price    DECIMAL(10,2)          COMMENT '最高价',
                        low_price     DECIMAL(10,2)          COMMENT '最低价',
                        pre_close     DECIMAL(10,2)          COMMENT '昨收价',
                        turnover_rate DECIMAL(10,2)          COMMENT '换手率%',
                        pe_ratio      DECIMAL(10,2)          COMMENT '市盈率',
                        pb_ratio      DECIMAL(10,2)          COMMENT '市净率',
                        total_mv      DECIMAL(18,2)          COMMENT '总市值',
                        circ_mv       DECIMAL(18,2)          COMMENT '流通市值',
                        volume_ratio  DECIMAL(10,2)          COMMENT '量比',
                        amplitude     DECIMAL(10,2)          COMMENT '振幅',
                        record_time   DATETIME      NOT NULL COMMENT '记录时间',
                        INDEX idx_stock_code (stock_code),
                        INDEX idx_record_time (record_time)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股票实时行情数据'
                """)
            self.conn.commit()
            log.info("数据表 stock_realtime 就绪")
        except Exception as e:
            log.error("创建表失败: %s", e)
            raise

    # ---- 连接管理 ----

    def ensure_connection(self):
        """确保数据库连接有效，否则重连"""
        try:
            if self.conn is None:
                self.conn = pymysql.connect(**self.db_config)
                return
            self.conn.ping(reconnect=True)
        except Exception:
            log.warning("数据库断连，尝试重连...")
            try:
                if self.conn:
                    self.conn.close()
            except Exception:
                pass
            self.conn = pymysql.connect(**self.db_config)
            log.info("数据库重连成功")

    # ---- 数据获取 ----

    def fetch_all_stocks(self):
        """获取全量A股实时行情，返回 DataFrame 或 None"""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log.info("正在获取全量A股实时数据 (第%d次)...", attempt)
                df = ak.stock_zh_a_spot_em()
                log.info("成功获取 %d 只股票数据", len(df))
                return df
            except Exception as e:
                log.warning("获取数据失败 (第%d次): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    time.sleep(3)
        log.error("达到最大重试次数，本次获取放弃")
        return None

    # ---- 数据保存 ----

    def save_to_database(self, df):
        """批量写入数据库"""
        if df is None or df.empty:
            log.warning("无数据可保存")
            return

        self.ensure_connection()

        now = datetime.now()
        rows = []
        for _, row in df.iterrows():
            values = []
            for ak_col in COLUMN_MAP:
                val = row.get(ak_col)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    values.append(None)
                    continue
                try:
                    # 数值转换
                    if ak_col in ('代码', '名称'):
                        values.append(str(val))
                    elif ak_col == '成交量':
                        values.append(int(float(val)))
                    else:
                        values.append(float(val))
                except (ValueError, TypeError):
                    values.append(None)
            values.append(now)
            rows.append(values)

        if not rows:
            return

        try:
            with self.conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
            self.conn.commit()
            log.info("成功写入 %d 条记录", len(rows))
        except Exception as e:
            log.error("写入数据库失败: %s", e)
            try:
                self.conn.rollback()
            except Exception:
                pass
            # 标记连接失效，下次自动重连
            self.conn = None

    # ---- 资源释放 ----

    def close(self):
        if self.conn:
            self.conn.close()
            log.info("数据库连接已关闭")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def is_trading_time(now: datetime) -> bool:
    """判断当前是否为A股连续竞价时间（周一至周五 9:30-11:30, 13:00-15:00）"""
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (TRADING_START_MORNING <= t <= TRADING_END_MORNING or
            TRADING_START_AFTER   <= t <= TRADING_END_AFTER)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    fetcher = StockDataFetcher()
    fetcher.create_database_and_tables()

    log.info("开始监控全量A股实时数据")
    log.info("交易时间轮询间隔: %ds  |  非交易时间轮询间隔: %ds",
             POLL_INTERVAL_TRADING, POLL_INTERVAL_NON_TRADING)
    log.info("=" * 60)

    try:
        while True:
            now = datetime.now()
            trading = is_trading_time(now)

            if trading:
                df = fetcher.fetch_all_stocks()
                if df is not None:
                    fetcher.save_to_database(df)
                sleep_sec = POLL_INTERVAL_TRADING
            else:
                sleep_sec = POLL_INTERVAL_NON_TRADING
                # 每5分钟在日志中输出一次等待提示
                if now.minute % 5 == 0 and now.second < sleep_sec:
                    log.info("非交易时间，%ds 后再次检查...", sleep_sec)

            time.sleep(sleep_sec)

    except KeyboardInterrupt:
        log.info("用户中断，程序退出")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
