from backtrader.brokers.easytradebroker import LiveTradingBroker
from backtrader.feeds.tushare import TushareRealTimeData
import logging
import datetime
import backtrader as bt

# 设置日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============== 3. 实盘交易策略 ===============
class RealTimeStrategy(bt.Strategy):
    """实盘交易策略"""

    params = (
        ("fast_ma_period", 10),  # 快速均线周期
        ("slow_ma_period", 30),  # 慢速均线周期
        ("trade_pct", 0.1),  # 每次交易资金比例
    )

    def __init__(self):
        # 初始化指标
        self.fast_ma = bt.indicators.SMA(period=self.p.fast_ma_period)
        self.slow_ma = bt.indicators.SMA(period=self.p.slow_ma_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

        # 交易状态
        self.order = None
        self.last_operation_time = None
        self.min_operation_interval = datetime.timedelta(minutes=5)  # 最小操作间隔

        logger.info("实盘交易策略初始化完成")

    def notify_order(self, order):
        """订单状态变化通知"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                logger.info(
                    f"买入成交: 价格 {order.executed.price}, 数量 {order.executed.size}"
                )
            elif order.issell():
                logger.info(
                    f"卖出成交: 价格 {order.executed.price}, 数量 {order.executed.size}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            logger.warning(f"订单未成交: {order.status}")

        self.order = None

    def next(self):
        """每个数据点到来时的策略逻辑"""
        # 检查是否有未完成的订单
        if self.order:
            return

        # 检查操作时间间隔
        current_time = datetime.datetime.now()
        if (
            self.last_operation_time is not None
            and current_time - self.last_operation_time < self.min_operation_interval
        ):
            return

        # 获取当前行情数据
        current_price = self.data.close[0]

        # 交易信号
        if self.crossover > 0:  # 金叉，买入信号
            # 计算交易数量
            cash = self.broker.getcash()
            trade_cash = cash * self.p.trade_pct
            size = int(trade_cash / current_price / 100) * 100  # 按手(100股)取整

            if size > 0:
                logger.info(f"买入信号: 价格={current_price}, 数量={size}")
                # 使用内置broker执行买入
                self.order = self.buy(size=size)
                self.last_operation_time = current_time

        elif self.crossover < 0:  # 死叉，卖出信号
            # 检查持仓
            position = self.getposition(self.data)
            if position.size > 0:
                logger.info(f"卖出信号: 价格={current_price}, 数量={position.size}")
                # 使用内置broker执行卖出
                self.order = self.sell(size=position.size)
                self.last_operation_time = current_time

    def stop(self):
        """策略结束时的处理"""
        logger.info("策略结束运行")


# =============== 4. 主程序 ===============
def run_real_time_trading(tushare_token, stock_code, broker_config):
    """运行实时交易主程序"""

    # 初始化Cerebro
    cerebro = bt.Cerebro()

    # 添加策略
    cerebro.addstrategy(RealTimeStrategy)

    # 创建实时数据源
    data = TushareRealTimeData(
        tushare_token=tushare_token,  # TuShare API token
        code=stock_code,  # 股票代码
        refresh_period=5,  # 5秒刷新一次
    )

    # 添加数据源
    cerebro.adddata(data, name=stock_code)

    # 创建实盘交易broker
    broker = LiveTradingBroker(
        broker_type=broker_config.get("type", "ths"),
        broker_id=broker_config.get("user", ""),
        broker_pw=broker_config.get("password", ""),
        broker_exe=broker_config.get("exe_path", ""),
    )

    # 替换默认broker
    cerebro.setbroker(broker)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    # 运行策略
    logger.info("开始实时交易...")
    results = cerebro.run()

    # 输出分析结果
    strat = results[0]
    logger.info(
        f"夏普比率: {strat.analyzers.sharpe.get_analysis().get('sharperatio', 0):.3f}"
    )
    logger.info(
        f"最大回撤: {strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0):.2f}%"
    )

    # 绘制结果图表
    cerebro.plot(style="candle", volume=True)


if __name__ == "__main__":
    # 配置信息
    tushare_token = (
        "d00a9271e726db72d5dcbc6edeabc9abeba3b4102aa1bb26cdadb20c"  # 替换为你的token
    )
    stock_code = "600519"  # 贵州茅台

    # 券商配置
    broker_config = {
        "type": "ths",  # 同花顺
        "user": "YOUR_USERNAME",  # 账户
        "password": "YOUR_PASSWORD",  # 密码
        "exe_path": "C:/同花顺安装路径/xiadan.exe",  # 交易软件路径
    }

    # 检查是否为交易时段
    now = datetime.datetime.now()
    weekday = now.weekday()

    # 只在工作日运行
    if weekday < 5:  # 0-4表示周一至周五
        current_time = now.time()
        morning_start = datetime.time(9, 30)
        morning_end = datetime.time(11, 30)
        afternoon_start = datetime.time(13, 0)
        afternoon_end = datetime.time(20, 0)

        # 检查是否在交易时段
        is_trading_time = (
            current_time >= morning_start and current_time <= morning_end
        ) or (current_time >= afternoon_start and current_time <= afternoon_end)

        if is_trading_time:
            run_real_time_trading(tushare_token, stock_code, broker_config)
        else:
            logger.info("当前不是交易时段，程序不启动")
    else:
        logger.info("今天是周末，不是交易日")
