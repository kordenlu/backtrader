from __future__ import absolute_import, division, print_function, unicode_literals

import backtrader as bt


class ChinaStockDecorator(bt.Sizer):
    """
    A股交易规则装饰器 - 可以包装任何现有的Sizer并添加100股整数倍的限制

    用法:
        cerebro.addsizer(ChinaStockDecorator, wrapped=bt.sizers.PercentSizer, percents=20)
    """

    params = (
        ("wrapped", None),  # 被包装的Sizer类
        ("minsize", 100),  # 最小交易单位
        # 允许传递任何参数到被包装的Sizer
    )

    def __init__(self):
        # 创建被包装的Sizer实例
        if self.p.wrapped is None:
            # 默认使用AllInSizerInt
            self.wrapped = bt.sizers.AllInSizerInt()
        else:
            # 收集除了'wrapped'和'minsize'之外的所有参数
            kwargs = {
                k: v
                for k, v in self.p._getkwargs().items()
                if k not in ["wrapped", "minsize"]
            }
            # 创建包装的Sizer实例
            self.wrapped = self.p.wrapped(**kwargs)

    def _getsizing(self, comminfo, cash, data, isbuy):
        # 获取包装的Sizer的尺寸建议
        size = self.wrapped._getsizing(comminfo, cash, data, isbuy)

        if isbuy:
            # 应用A股交易规则 - 向下取整到100的整数倍
            size = int(size / self.p.minsize) * self.p.minsize

            # 如果小于最小交易单位，则不交易
            if size < self.p.minsize:
                size = 0

        return size

    # 正确重写set方法来设置broker和strategy
    def set(self, strategy, broker):
        """
        重写set方法，确保broker和strategy传递给wrapped sizer
        """
        # 首先设置自己的broker和strategy
        self.strategy = strategy
        self.broker = broker

        # 然后设置wrapped sizer的broker和strategy
        self.wrapped.set(strategy, broker)

        return self

    def set_broker(self, broker):
        # 设置自己的broker
        self.broker = broker

        # 设置wrapped sizer的broker
        if hasattr(self.wrapped, "set_broker"):
            self.wrapped.set_broker(broker)

    def set_strategy(self, strategy):
        # 设置自己的strategy
        self.strategy = strategy

        # 设置wrapped sizer的strategy
        if hasattr(self.wrapped, "set_strategy"):
            self.wrapped.set_strategy(strategy)
