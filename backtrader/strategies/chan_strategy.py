import backtrader as bt
from backtrader.indicators.chan_theory import ChanTheoryIndicator


class ChanTheoryStrategy(bt.Strategy):
    params = (("printlog", False),)

    def __init__(self):
        # 应用缠论指标
        self.chan = ChanTheoryIndicator()

        self.chan.plotinfo.plot = True
        self.chan.plotinfo.subplot = True

        # 设置线条的绘制样式
        self.chan.plotlines.top_fractal._name = "Top Fractal"
        self.chan.plotlines.bottom_fractal._name = "Bottom Fractal"
        self.chan.plotlines.stroke_high._name = "Stroke High"
        self.chan.plotlines.stroke_low._name = "Stroke Low"
        self.chan.plotlines.hub_top._name = "Hub Upper"
        self.chan.plotlines.hub_bottom._name = "Hub Lower"

        self.trades_count = 0
        self.profitable_trades = 0

    def next(self):
        # 输出当前价格和缠论指标
        self.log(
            f"当前价格: {self.data0.close[0]:.2f}, 缠论指标: {self.chan.buy1[0]} {self.chan.buy2[0]} {self.chan.buy3[0]} {self.chan.sell1[0]} {self.chan.sell2[0]} {self.chan.sell3[0]}"
        )
        # 输出hub线
        self.log(f"Hub线: {self.chan.hub_top[0]:.2f} {self.chan.hub_bottom[0]:.2f}")
        # 没有持仓，检查买入信号
        if not self.position:
            # 一买信号
            if self.chan.buy1[0] > 0:
                self.buy()

            # 二买信号
            elif self.chan.buy2[0] > 0:
                self.buy()

            # 三买信号
            elif self.chan.buy3[0] > 0:
                self.buy()

        # 有持仓，检查卖出信号
        else:
            # 一卖信号
            if self.chan.sell1[0] > 0:
                self.sell()

            # 二卖信号
            elif self.chan.sell2[0] > 0:
                self.sell()

            # 三卖信号
            elif self.chan.sell3[0] > 0:
                self.sell()

    def log(self, txt, dt=None, doprint=False):
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()} {txt}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"买入执行, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}"
                )
            else:
                self.log(
                    f"卖出执行, 价格: {order.executed.price:.2f}, 成本: {order.executed.value:.2f}, 手续费: {order.executed.comm:.2f}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("订单被取消/拒绝")

    def notify_trade(self, trade):
        """记录交易完成后的利润"""
        if not trade.isclosed:
            return

        self.trades_count += 1

        gross_profit = trade.pnl  # 毛利润 (不计手续费)
        net_profit = trade.pnlcomm  # 净利润 (已减去手续费)

        if net_profit > 0:
            self.profitable_trades += 1

        self.log(
            f"交易完成, 毛利润: {gross_profit:.2f}, 净利润: {net_profit:.2f}, 手续费: {trade.commission:.2f}",
            doprint=True,
        )
        self.log(f"当前资金: {self.broker.getvalue():.2f}", doprint=True)

    def stop(self):
        """策略结束时的日志输出"""
        # 计算总体盈亏
        starting_value = self.broker.startingcash
        final_value = self.broker.getvalue()
        total_return = final_value - starting_value
        percent_return = (final_value / starting_value - 1.0) * 100

        # 输出总结
        self.log("=" * 50, doprint=True)
        self.log(f"策略执行完毕!", doprint=True)
        self.log(f"初始资金: {starting_value:.2f}", doprint=True)
        self.log(f"最终资金: {final_value:.2f}", doprint=True)
        self.log(f"总盈亏: {total_return:.2f} ({percent_return:.2f}%)", doprint=True)

        if self.trades_count > 0:
            win_rate = (self.profitable_trades / self.trades_count) * 100
            self.log(f"总交易次数: {self.trades_count}", doprint=True)
            self.log(f"盈利交易: {self.profitable_trades}", doprint=True)
            self.log(
                f"亏损交易: {self.trades_count - self.profitable_trades}", doprint=True
            )
            self.log(f"胜率: {win_rate:.2f}%", doprint=True)
        self.log("=" * 50, doprint=True)
