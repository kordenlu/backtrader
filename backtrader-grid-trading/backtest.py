from datetime import datetime
import backtrader as bt
from src.strategies.grid_strategy import GridStrategy
from config.settings import (
    INITIAL_CASH,
    COMMISSION,
    slippage,
    grid_size,
    take_profit,
    stop_loss,
    base_price,
)

if __name__ == "__main__":
    cerebro = bt.Cerebro(optreturn=False, maxcpus=1)

    # 设置初始资金
    cerebro.broker.setcash(INITIAL_CASH)
    # 设置滑点
    cerebro.broker.set_slippage_perc(slippage)

    # 添加数据
    try:
        # 修改日期到有效的过去日期
        data = bt.feeds.InfluxDB(
            symbol_code="002027",  # 替换为你的股票代码
            market="SZ",  # 替换为你的市场代码
            startdate="2022-01-01",  # 修改为有效的过去日期
            enddate="2022-12-31",  # 添加结束日期
            token="Pf4Rb2r0X7H5KscNkKMI3z9T4y7gZqGHoRGdE9hK9jqiihf2fKm2lTUa_qiQqWNMHBX-dXPYMIORMPMXf2j2Eg==",
            timeframe=bt.TimeFrame.Days,
        )
        cerebro.adddata(data)
    except Exception as e:
        print(f"加载数据出错: {e}")
        exit(1)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    # 简化参数优化范围
    cerebro.optstrategy(
        GridStrategy,
        grid_size=(0.01, 0.05, 0.03),  # 简化范围
        take_profit=(0.02,),
        stop_loss=(0.02,),
        base_price=(6, 7, 0.1),  # 使用None值，策略内部会处理
        position_sizing=("fixed", "percent"),  # 减少选项数量
    )

    # 设置佣金
    cerebro.broker.setcommission(commission=COMMISSION)

    # 打印初始资金
    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    # 运行回测
    results = cerebro.run()

    # 分析结果
    best_sharpe = -999.0
    best_params = None

    print("正在分析回测结果...")

    # 遍历所有回测结果
    for i, run in enumerate(results):
        # 获取夏普比率分析结果
        analysis = run[0].analyzers.sharpe.get_analysis()
        # 使用get方法安全地获取sharperatio，如果不存在返回None
        sharpe_ratio = analysis.get("sharperatio", None)

        # 打印当前参数组合的结果
        current_params = run[0].params
        print(
            f"参数组合 {i+1}: grid_size={current_params.grid_size}, "
            f"take_profit={current_params.take_profit}, "
            f"stop_loss={current_params.stop_loss}, "
            f"position_sizing={current_params.position_sizing}, "
            f"夏普比率: {sharpe_ratio}"
        )

        # 只有当sharpe_ratio不为None且大于当前最佳值时才更新
        if sharpe_ratio is not None and sharpe_ratio > best_sharpe:
            best_sharpe = sharpe_ratio
            best_params = current_params

    # 打印最终结果
    if best_params:
        print(
            f"\n最佳参数组合: grid_size={best_params.grid_size}, "
            f"take_profit={best_params.take_profit}, "
            f"stop_loss={best_params.stop_loss}, "
            f"position_sizing={best_params.position_sizing}"
        )
        print(f"最佳夏普比率: {best_sharpe}")
    else:
        print("未找到有效的参数组合。可能所有回测都未产生有效的夏普比率。")

    # 使用最佳参数运行单次回测并绘图
    if best_params:
        print("\n使用最佳参数运行完整回测...")
        cerebro_best = bt.Cerebro()
        cerebro_best.broker.setcash(INITIAL_CASH)
        cerebro_best.broker.set_slippage_perc(slippage)
        cerebro_best.broker.setcommission(commission=COMMISSION)
        cerebro_best.adddata(data)

        # 添加分析器以便查看详细结果
        cerebro_best.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
        cerebro_best.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro_best.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro_best.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

        # 使用最佳参数添加策略
        cerebro_best.addstrategy(
            GridStrategy,
            grid_size=best_params.grid_size,
            take_profit=best_params.take_profit,
            stop_loss=best_params.stop_loss,
            base_price=None,  # 使用策略内部处理
            position_sizing=best_params.position_sizing,
        )

        # 运行回测
        strats = cerebro_best.run()
        strat = strats[0]

        # 打印详细分析结果
        print("\n最佳策略分析结果:")
        print(f"最终资产: {cerebro_best.broker.getvalue():.2f}")
        print(
            f"夏普比率: {strat.analyzers.sharpe.get_analysis().get('sharperatio', 'N/A')}"
        )
        print(
            f"最大回撤: {strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 'N/A')}%"
        )
        print(
            f"年化收益率: {strat.analyzers.returns.get_analysis().get('ravg', 'N/A')*100:.2f}%"
        )

        # 交易详情
        trade_analysis = strat.analyzers.trades.get_analysis()
        print(f"总交易次数: {trade_analysis.get('total', {}).get('total', 0)}")
        print(f"盈利交易: {trade_analysis.get('won', {}).get('total', 0)}")
        print(f"亏损交易: {trade_analysis.get('lost', {}).get('total', 0)}")

        # 绘制图表
        cerebro_best.plot(style="candlestick")
