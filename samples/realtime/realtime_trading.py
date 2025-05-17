import sys
import os

# 添加backtrader根目录到Python路径
backtrader_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, backtrader_root)

import backtrader as bt
import yaml
import threading
import time as systime
from datetime import datetime, time
import argparse
import signal
import sys
import logging
from samples.realtime.buy_the_dip import BuyTheDip
from backtrader.sizers.chinastock_sizer import ChinaStockDecorator
from backtrader.feeds.tushare import TushareRealTimeData

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("realtime_trading.log"), logging.StreamHandler()],
)
logger = logging.getLogger("realtime_trading")

# 保存Cerebro实例，用于优雅退出
cerebro_instance = None


def signal_handler(sig, frame):
    """处理退出信号，优雅关闭交易系统"""
    logger.info("收到退出信号，正在关闭交易系统...")

    if cerebro_instance:
        # 关闭所有数据源
        for data in cerebro_instance.datas:
            if hasattr(data, "stop"):
                data.stop()

    logger.info("交易系统已关闭")
    sys.exit(0)


# filepath: [realtime_trading.py](http://_vscodecontentref_/1)
def monitor_trading_status(cerebro):
    """监控交易状态的线程函数"""
    current_thread = threading.current_thread()

    while not getattr(current_thread, "_stop_requested", False):
        try:
            broker = cerebro.broker
            # 修改这里，strategies只有在cerebro.run()后才可用
            strategies = getattr(cerebro, "runstrats", [])

            # 输出当前资产和持仓情况
            print("\n" + "=" * 50)
            print(f"当前时间: {datetime.now()}")
            print(f"账户价值: {broker.getvalue():.2f}")
            print(f"现金余额: {broker.getcash():.2f}")

            if strategies:
                for i, strategy in enumerate(strategies):
                    positions = {}
                    for data in strategy.datas:
                        pos = broker.getposition(data)
                        if pos.size != 0:
                            positions[data._name] = {
                                "size": pos.size,
                                "price": pos.price,
                                "value": pos.size * data.close[0],
                                "pnl": (data.close[0] - pos.price) * pos.size,
                            }

                    if positions:
                        print(f"\n策略 {i+1} 持仓:")
                        for symbol, details in positions.items():
                            print(
                                f"  {symbol}: {details['size']}股, "
                                f"成本价: {details['price']:.2f}, "
                                f"市值: {details['value']:.2f}, "
                                f"盈亏: {details['pnl']:.2f}"
                            )

            print("=" * 50)
        except Exception as e:
            print(f"监控异常: {e}")

        # 分段睡眠，便于响应停止请求
        for _ in range(60):
            if getattr(current_thread, "_stop_requested", False):
                break
            systime.sleep(1)

    print("监控线程已结束")


def run_realtime_trading(config_file):
    """启动实时交易系统"""
    global cerebro_instance

    # 加载配置
    with open(config_file, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    # 获取配置项
    realtime_config = config.get("realtime", {})
    default_strategy = config.get("default_strategy", {})
    stocks = config.get("stocks", [])

    # 创建Cerebro实例，启用实时模式
    cerebro = bt.Cerebro(live=True, stdstats=False)
    cerebro_instance = cerebro

    # 设置初始资金
    initial_cash = realtime_config.get("initial_cash", 100000.0)
    cerebro.broker.setcash(initial_cash)

    # 设置佣金
    commission = realtime_config.get("commission", 0.0003)
    cerebro.broker.setcommission(commission=commission)

    # 添加A股交易规则
    cerebro.addsizer(ChinaStockDecorator, wrapped=bt.sizers.AllInSizerInt)

    # 设置交易时区
    cerebro.addtz("Asia/Shanghai")

    data_feeds = []
    for stock in stocks:
        if stock.get("market", "") != "SH" and stock.get("market", "") != "SZ":
            logger.warning(
                f"跳过非A股市场股票: {stock['name']} ({stock['symbol_code']})"
            )
            continue

        logger.info(f"添加实时数据: {stock['name']} ({stock['symbol_code']})")

        # 创建TuShare实时数据源
        # 解析交易时间
        start_time_str = realtime_config.get("trading_hours", {}).get("start", "9:30")
        end_time_str = realtime_config.get("trading_hours", {}).get("end", "15:00")

        # 分别解析小时和分钟
        start_parts = start_time_str.split(":")
        end_parts = end_time_str.split(":")

        # 创建时间对象
        session_start = time(int(start_parts[0]), int(start_parts[1]))
        session_end = time(int(end_parts[0]), int(end_parts[1]))

        data = TushareRealTimeData(
            tushare_token=config.get("datasource", {}).get("token", ""),
            code=stock["symbol_code"],
            refresh_period=realtime_config.get("update_interval", 3),
            sessionstart=session_start,
            sessionend=session_end,
        )
        data_feeds.append((data, stock))
        cerebro.adddata(data, name=stock["symbol_code"])

    # 等待首个数据点获取
    systime.sleep(5)  # 给数据源一些时间获取初始数据

    # 为每只股票添加实时数据源
    # 然后添加策略
    for data, stock in data_feeds:
        strategy_params = default_strategy.copy()
        if "strategy" in stock:
            strategy_params.update(stock["strategy"])

        strategy_params["stock_name"] = stock["name"]
        cerebro.addstrategy(BuyTheDip, **strategy_params)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

    # 添加观察器
    cerebro.addobserver(bt.observers.Broker)
    cerebro.addobserver(bt.observers.BuySell)
    cerebro.addobserver(bt.observers.Value)

    # 启动交易系统
    logger.info(f"交易系统启动，初始资金: {initial_cash}")

    try:
        # 在实时模式下运行策略
        results = cerebro.run()
        print("启动交易状态监控...")
        monitor_thread = threading.Thread(
            target=monitor_trading_status, args=(cerebro,), daemon=True
        )
        monitor_thread._stop_requested = False
        monitor_thread.start()

        try:
            # 主线程持续运行，直到用户中断
            while True:
                systime.sleep(1)
        except KeyboardInterrupt:
            logger.info("用户中断，正在关闭交易系统...")
            # 通知监控线程停止
            monitor_thread._stop_requested = True
            # 给监控线程一些时间处理停止请求
            systime.sleep(2)

        # 在实时模式下，只有系统异常退出才会执行以下代码
        logger.info("交易系统运行结束")
        final_value = cerebro.broker.getvalue()
        logger.info(f"最终资产: {final_value:.2f}")
        logger.info(f"总收益率: {((final_value/initial_cash)-1)*100:.2f}%")

    except KeyboardInterrupt:
        logger.info("用户中断，正在关闭交易系统...")
    except Exception as e:
        logger.error(f"交易系统异常: {e}", exc_info=True)
    finally:
        # 确保所有数据源正确关闭
        for data in cerebro.datas:
            if hasattr(data, "stop"):
                data.stop()
        logger.info("交易系统已关闭")


if __name__ == "__main__":
    # 注册信号处理程序
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="A股实时交易系统")
    parser.add_argument(
        "-c",
        "--config",
        default="/Users/kordenlu/develop/python/backtrader/samples/realtime/config.yml",
        help="配置文件路径",
    )
    args = parser.parse_args()

    run_realtime_trading(args.config)
