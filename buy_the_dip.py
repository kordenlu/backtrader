import backtrader as bt
from datetime import datetime


class BuyTheDip(bt.Strategy):
    params = (
        ("dip", 6),  # 下跌幅度阈值
        ("hold", 60),  # 持股天数
        ("profit_target", 0.05),  # 盈利目标，1%
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.bar_executed = None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print("%s, %s" % (dt.isoformat(), txt))

    def next(self):
        # 检查是否有未完成的订单
        if self.order:
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
            # 计算下跌幅度
            today_close = self.dataclose[0]
            yesterday_close = self.dataclose[-1]
            if yesterday_close:
                dip_percentage = (yesterday_close - today_close) / yesterday_close * 100
            else:
                dip_percentage = 0  # 第一天无法计算下跌幅度

            # 检查是否下跌超过阈值
            if dip_percentage >= self.p.dip:
                # 买入
                self.log("BUY CREATE, %.2f" % self.dataclose[0])
                self.order = self.buy()
                self.buyprice = self.dataclose[0]
                self.bar_executed = len(self)

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    "BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f"
                    % (
                        order.executed.price,
                        getattr(order.executed, "cost", order.executed.price),
                        order.executed.comm,
                    )
                )

                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:  # Sell
                self.log(
                    "SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f"
                    % (
                        order.executed.price,
                        getattr(order.executed, "cost", order.executed.price),
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
    cerebro = bt.Cerebro()

    # 设置初始资金
    cerebro.broker.setcash(100000.0)

    # 添加数据
    data = bt.feeds.InfluxDB(
        symbol_code="600519",  # 替换为你的股票代码
        market="SH",  # 替换为你的市场代码
        startdate="2020-05-01",
        timeframe=bt.TimeFrame.Days,
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
    cerebro.plot(style="candlestick")
