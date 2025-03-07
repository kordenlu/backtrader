import backtrader as bt
import unittest

class TestGridStrategy(unittest.TestCase):
    def setUp(self):
        self.cerebro = bt.Cerebro()
        self.cerebro.addstrategy(GridStrategy)

        # 设置初始资金
        self.cerebro.broker.setcash(100000.0)

        # 添加数据
        data = bt.feeds.YahooFinanceData(
            dataname='AAPL',
            fromdate=datetime(2020, 1, 1),
            todate=datetime(2020, 12, 31)
        )
        self.cerebro.adddata(data)

    def test_strategy_execution(self):
        initial_value = self.cerebro.broker.getvalue()
        self.cerebro.run()
        final_value = self.cerebro.broker.getvalue()

        # 检查策略是否执行
        self.assertGreater(final_value, initial_value, "Strategy did not generate profit.")

    def test_grid_levels(self):
        # 这里可以添加测试网格级别的逻辑
        pass

if __name__ == '__main__':
    unittest.main()