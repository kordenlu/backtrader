import sys
import os

# 添加backtrader根目录到Python路径
backtrader_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, backtrader_root)
import backtrader as bt
import datetime
import pandas as pd
from backtrader.strategies.chan_strategy import ChanTheoryStrategy
from backtrader.sizers.chinastock_sizer import ChinaStockDecorator


def run_backtest():
    # 创建cerebro引擎
    cerebro = bt.Cerebro()

    cerebro.addsizer(ChinaStockDecorator, wrapped=bt.sizers.AllInSizerInt)

    # 添加数据
    data = bt.feeds.InfluxDB(
        symbol_code="01448",  # 替换为你的股票代码
        market="HK",  # 替换为你的市场代码
        startdate="2020-05-01",
        timeframe=bt.TimeFrame.Days,
        token="MXfDihY-IzKK_VMybAyzneHw8Yarj3dPG7axceYs2G1Tcfvm-7PeNVK7kgpx9OD5u6vzmiNwfp9tmIhw1bQmnA==",
    )
    cerebro.adddata(data)

    # 设置初始资金
    cerebro.broker.setcash(300000.0)

    # 设置手续费
    cerebro.broker.setcommission(commission=0.003)

    # 添加策略
    cerebro.addstrategy(ChanTheoryStrategy, printlog=True)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    # 运行回测
    print("开始资金: %.2f" % cerebro.broker.getvalue())
    results = cerebro.run()
    strat = results[0]

    # 打印最终结果
    print("最终资金: %.2f" % cerebro.broker.getvalue())
    print("夏普比率:", strat.analyzers.sharpe.get_analysis()["sharperatio"])
    print("最大回撤:", strat.analyzers.drawdown.get_analysis()["max"]["drawdown"])
    print("年化收益率:", strat.analyzers.returns.get_analysis()["rnorm100"])

    # 画图
    cerebro.plot(style="candlestick")


if __name__ == "__main__":
    run_backtest()
