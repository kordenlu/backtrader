import backtrader as bt
from datetime import datetime


class BuyTheDip(bt.Strategy):
    params = (
        ("dip", 2),  # 下跌幅度阈值
        ("hold", 30),  # 持股天数
        ("profit_target", 0.06),  # 盈利目标，5%
        ("price_threshold", 1550),  # 价格阈值
        ("stock_name", ""),  # 股票名称（用于日志）
        ("is_ashare", True),  # 默认为A股
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.bar_executed = None
        self.buy_dates = {}  # 跟踪买入日期

        # 添加实时交易所需变量
        self.last_check_time = None
        self.daily_trade_limit_reached = False
        self.trade_count = 0
        self.max_daily_trades = 5  # 每日最大交易次数

        # 显示当前股票的参数设置
        self.log(f"策略初始化: {self.p.stock_name}")
        self.log(
            f"参数: dip={self.p.dip}, hold={self.p.hold}, "
            f"profit_target={self.p.profit_target}, price_threshold={self.p.price_threshold}"
        )

    def log(self, txt, dt=None):
        """安全地记录日志，处理数据源为空的情况"""
        try:
            if self.datas and len(self.datas[0]) > 0:
                dt = dt or self.datas[0].datetime.date(0)
                print(f"{dt.isoformat()} {txt}")
            else:
                # 数据源为空时的处理
                print(f"[初始化] {txt}")
        except IndexError:
            # 处理索引错误
            print(f"[初始化] {txt}")

    def next(self):
        # 检查是否有未完成的订单
        if self.order:
            return

        # 实时交易安全检查
        current_time = datetime.now()
        current_date = current_time.date()

        # 每日交易限制重置
        if self.last_check_time and self.last_check_time.date() != current_date:
            self.daily_trade_limit_reached = False
            self.trade_count = 0

        self.last_check_time = current_time

        # 检查每日交易限制
        if self.daily_trade_limit_reached:
            return

        # 检查是否已经持仓
        if self.position:
            # 检查是否达到卖出日期
            # if len(self) >= (self.bar_executed + self.p.hold):
            #     # 卖出
            #     self.log("SELL CREATE, %.2f" % self.dataclose[0])
            #     self.order = self.close()
            # 检查是否达到盈利目标
            profit = (self.dataclose[0] - self.buyprice) / self.buyprice
            if profit >= self.p.profit_target:
                self.log("PROFIT TARGET REACHED, SELL CREATE, %.2f" % self.dataclose[0])
                self.order = self.close()
            # 检查是否达到持股天数，如果达到，也卖出
            elif len(self) >= (self.bar_executed + self.p.hold):
                self.log("HOLD PERIOD REACHED, SELL CREATE, %.2f" % self.dataclose[0])
                self.order = self.close()

        else:
            self.log("Close: %.2f" % self.dataclose[0])
            # 计算下跌幅度
            today_close = self.dataclose[0]
            yesterday_close = self.dataclose[-1]
            if yesterday_close:
                dip_percentage = (yesterday_close - today_close) / yesterday_close * 100
            else:
                dip_percentage = 0  # 第一天无法计算下跌幅度

            # 检查是否下跌超过阈值
            if (
                dip_percentage >= self.p.dip
                and self.dataclose[0] < self.p.price_threshold
                and self.trade_count < self.max_daily_trades
            ):
                # 全仓买入 (目标仓位为账户价值的100%)
                self.log(f"BUY CREATE (FULL POSITION), Price: {self.dataclose[0]:.2f}")
                self.order = self.buy()  # 1.0 表示 100%
                self.buyprice = self.dataclose[0]
                self.bar_executed = len(self)

                # 更新交易计数
                self.trade_count += 1
                if self.trade_count >= self.max_daily_trades:
                    self.daily_trade_limit_reached = True
                    self.log("每日交易次数限制已达到")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                cost = order.executed.price * order.executed.size
                self.log(
                    "BUY EXECUTED, Size: %d, Price: %.2f, Cost: %.2f, Comm %.2f"
                    % (
                        order.executed.size,  # 添加股数信息
                        order.executed.price,
                        cost,  # 总成本 = 价格 × 股数
                        order.executed.comm,
                    )
                )

                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:  # Sell
                # 手动计算订单成本
                cost = order.executed.price * abs(order.executed.size)
                self.log(
                    "SELL EXECUTED, Size: %d, Price: %.2f, Cost: %.2f, Comm %.2f"
                    % (
                        abs(order.executed.size),  # 对卖出取绝对值，使其为正数
                        order.executed.price,
                        cost,
                        order.executed.comm,
                    )
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("Order Canceled/Margin/Rejected")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log("OPERATION PROFIT, GROSS %.2f, NET %.2f" % (trade.pnl, trade.pnlcomm))


if __name__ == "__main__":
    cerebro = bt.Cerebro(live=True)

    # 设置初始资金
    cerebro.broker.setcash(100000.0)

    # 添加数据
    data = bt.feeds.InfluxDB(
        symbol_code="03319",  # 替换为你的股票代码
        market="HK",  # 替换为你的市场代码
        startdate="2020-05-01",
        timeframe=bt.TimeFrame.Days,
        token="MXfDihY-IzKK_VMybAyzneHw8Yarj3dPG7axceYs2G1Tcfvm-7PeNVK7kgpx9OD5u6vzmiNwfp9tmIhw1bQmnA==",
    )
    cerebro.adddata(data)

    # 添加策略
    cerebro.addstrategy(BuyTheDip)

    # 设置佣金
    cerebro.broker.setcommission(commission=0.0003)  # 假设佣金为 0.1%

    # 打印初始资金
    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    # 运行回测
    cerebro.run()

    # 打印最终资金
    print("Final Portfolio Value: %.2f" % cerebro.broker.getvalue())

    # 绘制图表
    # cerebro.plot(style="candlestick")
