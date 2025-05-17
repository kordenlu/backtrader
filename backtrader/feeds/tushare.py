import backtrader as bt
import datetime
import time
import tushare as ts
import logging
import queue
import threading

# 设置日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============== 1. TuShare实时数据源 ===============
class TushareRealTimeData(bt.feeds.DataBase):
    """TuShare实时数据源"""

    lines = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "openinterest",
    )  # 定义数据线

    params = (
        ("tushare_token", ""),  # 你的TuShare API token
        ("code", ""),  # 股票代码
        ("refresh_period", 3),  # 数据刷新周期(秒)
        ("sessionstart", datetime.time(9, 30)),  # 交易开始时间
        ("sessionend", datetime.time(20, 0)),  # 交易结束时间
    )

    def __init__(self):
        self.tushare_api = ts.pro_api(self.p.tushare_token)
        self.data_q = queue.Queue(20)
        self.trading_active = True
        self.last_bar_time = None
        # 初始化_laststatus属性
        self._laststatus = self.DELAYED  # 初始设置为DELAYED状态

        # 启动数据获取线程
        self.data_thread = threading.Thread(target=self._data_pusher)
        self.data_thread.daemon = True
        self.data_thread.start()

        # 初始化父类
        super(TushareRealTimeData, self).__init__()

        # 在现有类中添加以下函数

    def start(self):
        """启动数据源时被调用"""
        logger.info(f"启动TuShare实时数据源: {self.p.code}")
        self._laststatus = self.LIVE  # 设置状态为LIVE
        super(TushareRealTimeData, self).start()

    def islive(self):
        """告诉backtrader这是实时数据源"""
        return True

    def haslivedata(self):
        """告诉backtrader数据源是否有实时数据可用"""
        return not self.data_q.empty()

    def _get_historical_data(self):
        """获取历史数据，以便提供足够的历史上下文"""
        try:
            # 获取最近30天的日线数据
            end_date = datetime.datetime.now().strftime("%Y%m%d")
            start_date = (
                datetime.datetime.now() - datetime.timedelta(days=30)
            ).strftime("%Y%m%d")

            df = self.tushare_api.daily(
                ts_code=f"{self.p.code}.{'SH' if self.p.code.startswith('6') else 'SZ'}",
                start_date=start_date,
                end_date=end_date,
            )

            if df is not None and not df.empty:
                # 转换日期并排序
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df = df.sort_values("trade_date")

                # 填充历史数据队列
                for _, row in df.iterrows():
                    data = {
                        "datetime": row["trade_date"],
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["vol"]),
                        "openinterest": 0.0,
                    }
                    self.data_q.put(data)

                logger.info(f"加载了{len(df)}条历史数据")

        except Exception as e:
            logger.error(f"获取历史数据出错: {e}")

    def _data_pusher(self):
        """在单独的线程中获取实时数据"""
        while self.trading_active:
            try:
                logger.debug("获取实时数据...")
                now = datetime.datetime.now()
                current_time = now.time()

                # 检查是否在交易时段内
                is_trading_time = (
                    current_time >= self.p.sessionstart
                    and current_time <= self.p.sessionend
                ) and (
                    now.weekday() < 5
                )  # 周一到周五

                if is_trading_time:
                    try:
                        # 获取实时行情数据
                        code = self.p.code
                        if code.startswith("6"):
                            full_code = f"sh{code}"
                        else:
                            full_code = f"sz{code}"

                        # 使用TuShare获取实时行情
                        df = ts.get_realtime_quotes(full_code)
                        if df is not None and not df.empty:
                            data = {
                                "datetime": now,
                                "open": float(df.at[0, "open"]),
                                "high": float(df.at[0, "high"]),
                                "low": float(df.at[0, "low"]),
                                "close": float(df.at[0, "price"]),
                                "volume": float(df.at[0, "volume"]),
                                "openinterest": 0.0,
                            }
                            self.data_q.put(data)
                            logger.debug(f"获取到实时数据: {data}")
                            # 添加通知机制，告知Cerebro有新数据
                            self.put_notification(self.LIVE)
                    except Exception as e:
                        logger.error(f"获取实时数据出错: {e}")

                # 等待下次刷新
                time.sleep(self.p.refresh_period)
            except Exception as e:
                # 捕获所有可能的异常，防止线程意外退出
                logger.error(f"数据线程发生严重错误: {e}", exc_info=True)
                time.sleep(5)  # 避免错误频繁重复，增加等待时间

        logger.info(f"数据获取线程已结束: {self.p.code}")

    def stop(self):
        """停止数据源线程"""
        logger.info(f"停止TuShare实时数据源: {self.p.code}")
        self.trading_active = False
        if hasattr(self, "data_thread") and self.data_thread.is_alive():
            self.data_thread.join(timeout=10)
        super(TushareRealTimeData, self).stop()

    def _load(self):
        """获取并加载下一个数据条"""
        try:
            # 非阻塞方式获取数据
            if not self.data_q.empty():
                data = self.data_q.get(block=False)

                # 避免重复数据
                if (
                    self.last_bar_time is not None
                    and data["datetime"] == self.last_bar_time
                ):
                    return None

                # 更新最后数据时间
                self.last_bar_time = data["datetime"]

                # 填充数据线
                self.lines.datetime[0] = bt.date2num(data["datetime"])
                self.lines.open[0] = data["open"]
                self.lines.high[0] = data["high"]
                self.lines.low[0] = data["low"]
                self.lines.close[0] = data["close"]
                self.lines.volume[0] = data["volume"]
                self.lines.openinterest[0] = data["openinterest"]

                self._laststatus = self.LIVE

                return True

            return None  # 没有新数据

        except Exception as e:
            logger.error(f"加载实时数据出错: {e}")
            return None
