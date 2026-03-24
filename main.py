# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 主调度程序
===================================

职责：
1. 协调各模块完成股票分析流程
2. 实现低并发的线程池调度
3. 全局异常处理，确保单股失败不影响整体
4. 提供命令行入口

使用方式：
    python main.py              # 正常运行
    python main.py --debug      # 调试模式
    python main.py --dry-run    # 仅获取数据不分析

交易理念（已融入分析）：
- 严进策略：不追高，乖离率 > 5% 不买入
- 趋势交易：只做 MA5>MA10>MA20 多头排列
- 效率优先：关注筹码集中度好的股票
- 买点偏好：缩量回踩 MA5/MA10 支撑
"""
import os
from src.config import setup_env
setup_env()

# 代理配置 - 通过 USE_PROXY 环境变量控制，默认关闭
# GitHub Actions 环境自动跳过代理配置
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # 本地开发环境，启用代理（可在 .env 中配置 PROXY_HOST 和 PROXY_PORT）
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from data_provider.base import canonical_stock_code
from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review
from src.webui_frontend import prepare_webui_frontend_assets
from src.config import get_config, Config
from src.logging_config import setup_logging


logger = logging.getLogger(__name__)


# Tool alias mapping
TOOL_ALIASES = {
    # Data tools
    'quote': 'get_realtime_quote',
    'history': 'get_daily_history',
    'chip': 'get_chip_distribution',
    'context': 'get_analysis_context',
    'info': 'get_stock_info',
    # Analysis tools
    'trend': 'analyze_trend',
    'ma': 'calculate_ma',
    'volume': 'get_volume_analysis',
    'pattern': 'analyze_pattern',
    # Market tools
    'indices': 'get_market_indices',
    'sectors': 'get_sector_rankings',
    # Search tools
    'news': 'search_stock_news',
    'intel': 'search_comprehensive_intel',
}


def execute_single_tool(tool_alias: str, args: argparse.Namespace) -> dict:
    """
    Execute a single agent tool
    
    Args:
        tool_alias: Tool alias (e.g., 'quote', 'ma', 'trend')
        args: Command line arguments
        
    Returns:
        Tool execution result (dict format)
    """
    # Map alias to full tool name
    tool_name = TOOL_ALIASES.get(tool_alias)
    if tool_name is None:
        return {"error": f"Unknown tool alias: {tool_alias}"}
    
    # Get stock code from --stocks parameter (support single code only for tools)
    stock_code = None
    if args.stocks:
        stock_code = args.stocks.split(',')[0].strip()
    
    # Tools that require historical data in database
    TOOLS_NEED_DB_DATA = ['analyze_trend', 'get_analysis_context']
    
    # Auto-fetch and save data for tools that need it
    if tool_name in TOOLS_NEED_DB_DATA and stock_code:
        logger.info(f"[Tool] {tool_name} requires historical data, fetching for {stock_code}...")
        try:
            from data_provider import DataFetcherManager
            from src.storage import get_db
            
            manager = DataFetcherManager()
            db = get_db()
            
            # Fetch historical data
            df, source = manager.get_daily_data(stock_code, days=120)
            if df is not None and not df.empty:
                # Save to database
                saved_count = db.save_daily_data(df, stock_code, source)
                logger.info(f"[Tool] Saved {saved_count} new records for {stock_code} from {source}")
                
                # For analyze_trend, also prepare raw_data in context
                if tool_name == "analyze_trend":
                    # Get context and add raw_data
                    context = db.get_analysis_context(stock_code)
                    if context:
                        # Get recent data from DB and convert to list of dicts
                        recent_records = db.get_latest_data(stock_code, days=120)
                        if recent_records:
                            raw_data = [rec.to_dict() for rec in recent_records]
                            context['raw_data'] = raw_data
                            logger.info(f"[Tool] Prepared {len(raw_data)} days of raw_data for trend analysis")
            else:
                logger.warning(f"[Tool] Failed to fetch data for {stock_code}")
        except Exception as e:
            logger.error(f"[Tool] Error fetching data for {stock_code}: {e}")
    
    # ============================================================
    # Data Tools
    # ============================================================
    
    if tool_name == "get_realtime_quote":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.data_tools import _handle_get_realtime_quote
        return _handle_get_realtime_quote(stock_code)
    
    elif tool_name == "get_daily_history":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.data_tools import _handle_get_daily_history
        days = args.days if args.days else 60
        return _handle_get_daily_history(stock_code, days)
    
    elif tool_name == "get_chip_distribution":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.data_tools import _handle_get_chip_distribution
        return _handle_get_chip_distribution(stock_code)
    
    elif tool_name == "get_analysis_context":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.data_tools import _handle_get_analysis_context
        return _handle_get_analysis_context(stock_code)
    
    elif tool_name == "get_stock_info":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.data_tools import _handle_get_stock_info
        return _handle_get_stock_info(stock_code)
    
    # ============================================================
    # Analysis Tools
    # ============================================================
    
    elif tool_name == "analyze_trend":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.analysis_tools import _handle_analyze_trend
        return _handle_analyze_trend(stock_code)
    
    elif tool_name == "calculate_ma":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.analysis_tools import _handle_calculate_ma
        periods = args.periods if args.periods else None
        days = args.days if args.days else 120
        return _handle_calculate_ma(stock_code, periods, days)
    
    elif tool_name == "get_volume_analysis":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.analysis_tools import _handle_get_volume_analysis
        days = args.days if args.days else 30
        return _handle_get_volume_analysis(stock_code, days)
    
    elif tool_name == "analyze_pattern":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        from src.agent.tools.analysis_tools import _handle_analyze_pattern
        days = args.days if args.days else 60
        return _handle_analyze_pattern(stock_code, days)
    
    # ============================================================
    # Market Tools
    # ============================================================
    
    elif tool_name == "get_market_indices":
        from src.agent.tools.market_tools import _handle_get_market_indices
        region = args.region if args.region else "cn"
        return _handle_get_market_indices(region)
    
    elif tool_name == "get_sector_rankings":
        from src.agent.tools.market_tools import _handle_get_sector_rankings
        top_n = args.top_n if hasattr(args, 'top_n') and args.top_n else 10
        return _handle_get_sector_rankings(top_n)
    
    # ============================================================
    # Search Tools
    # ============================================================
    
    elif tool_name == "search_stock_news":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        if not args.name:
            return {"error": "Missing required parameter: --name"}
        from src.agent.tools.search_tools import _handle_search_stock_news
        return _handle_search_stock_news(stock_code, args.name)
    
    elif tool_name == "search_comprehensive_intel":
        if not stock_code:
            return {"error": "Missing required parameter: --stocks"}
        if not args.name:
            return {"error": "Missing required parameter: --name"}
        from src.agent.tools.search_tools import _handle_search_comprehensive_intel
        return _handle_search_comprehensive_intel(stock_code, args.name)
    
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='A股自选股智能分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常运行
  python main.py --debug            # 调试模式
  python main.py --dry-run          # 仅获取数据，不进行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --no-notify        # 不发送推送通知
  python main.py --single-notify    # 启用单股推送模式（每分析完一只立即推送）
  python main.py --schedule         # 启用定时任务模式
  python main.py --market-review    # 仅运行大盘复盘
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅获取数据，不进行 AI 分析'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代码，逗号分隔（覆盖配置文件）'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送推送通知'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='启用单股推送模式：每分析完一只股票立即推送，而不是汇总推送'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发线程数（默认使用配置值）'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式，每日定时执行'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='定时任务启动时不立即执行一次'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='仅运行大盘复盘分析'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳过大盘复盘分析'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='跳过交易日检查，强制执行全量分析（Issue #373）'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='启动 Web 管理界面'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='仅启动 Web 服务，不执行自动分析'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='启动 FastAPI 后端服务（同时执行分析任务）'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='仅启动 FastAPI 后端服务，不自动执行分析'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='FastAPI 服务端口（默认 8000）'
    )

    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='FastAPI 服务监听地址（默认 0.0.0.0）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='不保存分析上下文快照'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='运行回测（对历史分析结果进行评估）'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='仅回测指定股票代码'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='回测评估窗口（交易日数，默认使用配置）'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='强制回测（即使已有回测结果也重新计算）'
    )

    # === Tool Execution ===
    parser.add_argument(
        '--tool',
        type=str,
        choices=[
            # Data tools
            'quote', 'history', 'chip', 'context', 'info',
            # Analysis tools
            'trend', 'ma', 'volume', 'pattern',
            # Market tools
            'indices', 'sectors',
            # Search tools
            'news', 'intel',
        ],
        help=(
            '执行单个 Agent 工具，直接输出结构化结果（默认 JSON）。\n'
            '\n'
            '数据工具（需要 --stocks）:\n'
            '  quote    实时行情\n'
            '  history  历史K线  [--days N，默认60]\n'
            '  chip     筹码分布\n'
            '  context  分析上下文（自动拉取历史数据）\n'
            '  info     股票基本面信息\n'
            '\n'
            '分析工具（需要 --stocks）:\n'
            '  trend    技术趋势分析（自动拉取历史数据）\n'
            '  ma       均线计算  [--periods 5,10,20,60] [--days N，默认120]\n'
            '  volume   量能分析  [--days N，默认30]\n'
            '  pattern  形态识别  [--days N，默认60]\n'
            '\n'
            '市场工具（无需 --stocks）:\n'
            '  indices  市场指数  [--region cn|us，默认cn]\n'
            '  sectors  板块排名  [--top-n N，默认10]\n'
            '\n'
            '搜索工具（需要 --stocks 和 --name）:\n'
            '  news     股票新闻搜索\n'
            '  intel    综合情报搜索\n'
            '\n'
            '示例:\n'
            '  python main.py --tool quote   --stocks 600519\n'
            '  python main.py --tool trend   --stocks 600519 --output-format json\n'
            '  python main.py --tool ma      --stocks 600519 --periods 5,10,20,60\n'
            '  python main.py --tool volume  --stocks 600519 --days 30\n'
            '  python main.py --tool indices --region cn\n'
            '  python main.py --tool sectors --top-n 5\n'
            '  python main.py --tool news    --stocks 600519 --name 贵州茅台\n'
        )
    )

    parser.add_argument(
        '--name',
        type=str,
        help='股票名称（用于搜索工具）'
    )

    parser.add_argument(
        '--region',
        type=str,
        choices=['cn', 'us'],
        default='cn',
        help='市场区域（用于市场指数查询，默认 cn）'
    )

    parser.add_argument(
        '--periods',
        type=str,
        help='均线周期，逗号分隔，如 "5,10,20,60"（用于均线计算）'
    )

    parser.add_argument(
        '--days',
        type=int,
        help='天数参数（用于历史数据、量能分析、形态识别等）'
    )

    parser.add_argument(
        '--top-n',
        type=int,
        default=10,
        help='返回数量（用于板块排名，默认 10）'
    )

    parser.add_argument(
        '--output-format',
        type=str,
        choices=['json', 'text', 'table'],
        default='json',
        help='输出格式（默认 json）'
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        '--output-file',
        type=str,
        help='将结果写入指定文件路径（适用于工具输出或主流程报告）'
    )
    output_group.add_argument(
        '--output-dir',
        type=str,
        help='将结果写入指定目录（文件名自动生成或沿用默认报告名）'
    )

    return parser.parse_args()


def _write_output_text(output_path: str, content: str) -> str:
    """Write rendered output to the target file path."""
    target_path = Path(output_path).expanduser()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding='utf-8')
    return str(target_path)


def _render_tool_result(result: dict, output_format: str) -> str:
    """Render single-tool result to string according to selected output format."""
    if output_format == "json":
        import json
        import datetime as _dt

        class _DateEncoder(json.JSONEncoder):
            """JSON encoder that handles date/datetime objects."""
            def default(self, o):
                if isinstance(o, (_dt.date, _dt.datetime)):
                    return o.isoformat()
                return super().default(o)

        return json.dumps(result, ensure_ascii=False, indent=2, cls=_DateEncoder)

    if output_format == "text":
        if "error" in result:
            return f"Error: {result['error']}"
        return "\n".join(f"{key}: {value}" for key, value in result.items())

    if output_format == "table":
        try:
            from tabulate import tabulate
            if isinstance(result, dict) and not result.get("error"):
                return tabulate(result.items(), headers=["Field", "Value"], tablefmt="grid")
            return str(result)
        except ImportError:
            logger.warning("tabulate not installed, falling back to text format")
            return "\n".join(f"{key}: {value}" for key, value in result.items())

    raise ValueError(f"Unsupported output format: {output_format}")


def _build_tool_output_path(args: argparse.Namespace) -> Optional[str]:
    """Resolve output file path for single-tool mode when file output is requested."""
    if getattr(args, 'output_file', None):
        return args.output_file
    if not getattr(args, 'output_dir', None):
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = '.json' if args.output_format == 'json' else '.txt'
    filename = f"{args.tool}_{timestamp}{suffix}"
    return str(Path(args.output_dir).expanduser() / filename)


def _validate_output_options(args: argparse.Namespace, config: Config) -> None:
    """Validate output options that depend on runtime mode and config."""
    if not getattr(args, 'output_file', None):
        return

    if args.tool or args.market_review:
        return

    if getattr(args, 'no_market_review', False) or not getattr(config, 'market_review_enabled', True):
        return

    raise ValueError(
        "--output-file 在当前模式下会同时生成个股报告和大盘复盘，"
        "请改用 --output-dir，或配合 --no-market-review 仅输出单个文件。"
    )


def _compute_trading_day_filter(
    config: Config,
    args: argparse.Namespace,
    stock_codes: List[str],
) -> Tuple[List[str], Optional[str], bool]:
    """
    Compute filtered stock list and effective market review region (Issue #373).

    Returns:
        (filtered_codes, effective_region, should_skip_all)
        - effective_region None = use config default (check disabled)
        - effective_region '' = all relevant markets closed, skip market review
        - should_skip_all: skip entire run when no stocks and no market review to run
    """
    force_run = getattr(args, 'force_run', False)
    if force_run or not getattr(config, 'trading_day_check_enabled', True):
        return (stock_codes, None, False)

    from src.core.trading_calendar import (
        get_market_for_stock,
        get_open_markets_today,
        compute_effective_region,
    )

    open_markets = get_open_markets_today()
    filtered_codes = []
    for code in stock_codes:
        mkt = get_market_for_stock(code)
        if mkt in open_markets or mkt is None:
            filtered_codes.append(code)

    if config.market_review_enabled and not getattr(args, 'no_market_review', False):
        effective_region = compute_effective_region(
            getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
        )
    else:
        effective_region = None

    should_skip_all = (not filtered_codes) and (effective_region or '') == ''
    return (filtered_codes, effective_region, should_skip_all)


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None
):
    """
    执行完整的分析流程（个股 + 大盘复盘）

    这是定时任务调用的主函数
    """
    try:
        # Issue #529: Hot-reload STOCK_LIST from .env on each scheduled run
        if stock_codes is None:
            config.refresh_stock_list()

        # Issue #373: Trading day filter (per-stock, per-market)
        effective_codes = stock_codes if stock_codes is not None else config.stock_list
        filtered_codes, effective_region, should_skip = _compute_trading_day_filter(
            config, args, effective_codes
        )
        if should_skip:
            logger.info(
                "今日所有相关市场均为非交易日，跳过执行。可使用 --force-run 强制执行。"
            )
            return
        if set(filtered_codes) != set(effective_codes):
            skipped = set(effective_codes) - set(filtered_codes)
            logger.info("今日休市股票已跳过: %s", skipped)
        stock_codes = filtered_codes

        # 命令行参数 --single-notify 覆盖配置（#55）
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True

        # Issue #190: 个股与大盘复盘合并推送
        merge_notification = (
            getattr(config, 'merge_email_notification', False)
            and config.market_review_enabled
            and not getattr(args, 'no_market_review', False)
            and not config.single_stock_notify
        )

        # 创建调度器
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot,
            report_output_dir=getattr(args, 'output_dir', None),
            report_output_file=getattr(args, 'output_file', None),
        )

        # 1. 运行个股分析
        results = pipeline.run(
            stock_codes=stock_codes,
            dry_run=args.dry_run,
            send_notification=not args.no_notify,
            merge_notification=merge_notification
        )

        # Issue #128: 分析间隔 - 在个股分析和大盘分析之间添加延迟
        analysis_delay = getattr(config, 'analysis_delay', 0)
        if (
            analysis_delay > 0
            and config.market_review_enabled
            and not args.no_market_review
            and effective_region != ''
        ):
            logger.info(f"等待 {analysis_delay} 秒后执行大盘复盘（避免API限流）...")
            time.sleep(analysis_delay)

        # 2. 运行大盘复盘（如果启用且不是仅个股模式）
        market_report = ""
        if (
            config.market_review_enabled
            and not args.no_market_review
            and effective_region != ''
        ):
            review_result = run_market_review(
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service,
                send_notification=not args.no_notify,
                merge_notification=merge_notification,
                override_region=effective_region,
            )
            # 如果有结果，赋值给 market_report 用于后续飞书文档生成
            if review_result:
                market_report = review_result

        # Issue #190: 合并推送（个股+大盘复盘）
        if merge_notification and (results or market_report) and not args.no_notify:
            parts = []
            if market_report:
                parts.append(f"# 📈 大盘复盘\n\n{market_report}")
            if results:
                dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                parts.append(f"# 🚀 个股决策仪表盘\n\n{dashboard_content}")
            if parts:
                combined_content = "\n\n---\n\n".join(parts)
                if pipeline.notifier.is_available():
                    if pipeline.notifier.send(combined_content, email_send_to_all=True):
                        logger.info("已合并推送（个股+大盘复盘）")
                    else:
                        logger.warning("合并推送失败")

        # 输出摘要
        if results:
            logger.info("\n===== 分析结果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )

        logger.info("\n任务执行完成")

        # === 新增：生成飞书云文档 ===
        try:
            from src.feishu_doc import FeishuDocManager

            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在创建飞书云文档...")

                # 1. 准备标题 "01-01 13:01大盘复盘"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盘复盘"

                # 2. 准备内容 (拼接个股分析和大盘复盘)
                full_content = ""

                # 添加大盘复盘内容（如果有）
                if market_report:
                    full_content += f"# 📈 大盘复盘\n\n{market_report}\n\n---\n\n"

                # 添加个股决策仪表盘（使用 NotificationService 生成）
                if results:
                    dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                    full_content += f"# 🚀 个股决策仪表盘\n\n{dashboard_content}"

                # 3. 创建文档
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飞书云文档创建成功: {doc_url}")
                    # 可选：将文档链接也推送到群里
                    if not args.no_notify:
                        pipeline.notifier.send(f"[{now.strftime('%Y-%m-%d %H:%M')}] 复盘文档创建成功: {doc_url}")

        except Exception as e:
            logger.error(f"飞书文档生成失败: {e}")

        # === Auto backtest ===
        try:
            if getattr(config, 'backtest_enabled', False):
                from src.services.backtest_service import BacktestService

                logger.info("开始自动回测...")
                service = BacktestService()
                stats = service.run_backtest(
                    force=False,
                    eval_window_days=getattr(config, 'backtest_eval_window_days', 10),
                    min_age_days=getattr(config, 'backtest_min_age_days', 14),
                    limit=200,
                )
                logger.info(
                    f"自动回测完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                    f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
                )
        except Exception as e:
            logger.warning(f"自动回测失败（已忽略）: {e}")

    except Exception as e:
        logger.exception(f"分析流程执行失败: {e}")


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    在后台线程启动 FastAPI 服务
    
    Args:
        host: 监听地址
        port: 监听端口
        config: 配置对象
    """
    import threading
    import uvicorn

    def run_server():
        level_name = (config.log_level or "INFO").lower()
        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            log_level=level_name,
            log_config=None,
        )

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info(f"FastAPI 服务已启动: http://{host}:{port}")


def _is_truthy_env(var_name: str, default: str = "true") -> bool:
    """Parse common truthy / falsy environment values."""
    value = os.getenv(var_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}

def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # 启动钉钉 Stream 客户端
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # 启动飞书 Stream 客户端
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def main() -> int:
    """
    主入口函数

    Returns:
        退出码（0 表示成功）
    """
    # 解析命令行参数
    args = parse_arguments()

    # 加载配置（在设置日志前加载，以获取日志目录）
    config = get_config()
    try:
        _validate_output_options(args, config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # 配置日志（输出到控制台和文件）
    setup_logging(log_prefix="stock_analysis", debug=args.debug, log_dir=config.log_dir)

    logger.info("=" * 60)
    logger.info("A股自选股智能分析系统 启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # ============================================================
    # Mode 0: Single Tool Execution (NEW)
    # ============================================================
    if args.tool:
        logger.info(f"模式: 单工具执行 ({args.tool})")
        
        # Execute tool
        result = execute_single_tool(args.tool, args)
        
        output_format = getattr(args, 'output_format', 'json')
        rendered_output = _render_tool_result(result, output_format)
        output_path = _build_tool_output_path(args)

        if output_path:
            saved_path = _write_output_text(output_path, rendered_output)
            logger.info(f"工具结果已写入: {saved_path}")
        else:
            print(rendered_output)

        return 0 if "error" not in result else 1

    # ============================================================
    # Continue with existing modes
    # ============================================================

    # 验证配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    # 解析股票列表（统一为大写 Issue #355）
    stock_codes = None
    if args.stocks:
        stock_codes = [canonical_stock_code(c) for c in args.stocks.split(',') if (c or "").strip()]
        logger.info(f"使用命令行指定的股票列表: {stock_codes}")

    # === 处理 --webui / --webui-only 参数，映射到 --serve / --serve-only ===
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # 兼容旧版 WEBUI_ENABLED 环境变量
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # === 启动 Web 服务 (如果启用) ===
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    # 兼容旧版 WEBUI_HOST/WEBUI_PORT：如果用户未通过 --host/--port 指定，则使用旧变量
    if start_serve:
        if args.host == '0.0.0.0' and os.getenv('WEBUI_HOST'):
            args.host = os.getenv('WEBUI_HOST')
        if args.port == 8000 and os.getenv('WEBUI_PORT'):
            args.port = int(os.getenv('WEBUI_PORT'))

    bot_clients_started = False
    if start_serve:
        if not prepare_webui_frontend_assets():
            logger.warning("前端静态资源未就绪，继续启动 FastAPI 服务（Web 页面可能不可用）")
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as e:
            logger.error(f"启动 FastAPI 服务失败: {e}")

    if bot_clients_started:
        start_bot_stream_clients(config)

    # === 仅 Web 服务模式：不自动执行分析 ===
    if args.serve_only:
        logger.info("模式: 仅 Web 服务")
        logger.info(f"Web 服务运行中: http://{args.host}:{args.port}")
        logger.info("通过 /api/v1/analysis/stock/{code} 接口触发分析")
        logger.info(f"API 文档: http://{args.host}:{args.port}/docs")
        logger.info("按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n用户中断，程序退出")
        return 0

    try:
        # 模式0: 回测
        if getattr(args, 'backtest', False):
            logger.info("模式: 回测")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"回测完成: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # 模式1: 仅大盘复盘
        if args.market_review:
            from src.analyzer import GeminiAnalyzer
            from src.core.market_review import run_market_review
            from src.notification import NotificationService
            from src.search_service import SearchService

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info("今日大盘复盘相关市场均为非交易日，跳过执行。可使用 --force-run 强制执行。")
                    return 0

            logger.info("模式: 仅大盘复盘")
            notifier = NotificationService(
                report_output_dir=getattr(args, 'output_dir', None),
                report_output_file=getattr(args, 'output_file', None),
            )

            # 初始化搜索服务和分析器（如果有配置）
            search_service = None
            analyzer = None

            if config.bocha_api_keys or config.tavily_api_keys or config.brave_api_keys or config.serpapi_keys:
                search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys,
                    news_max_age_days=config.news_max_age_days,
                )

            if config.gemini_api_key or config.openai_api_key:
                analyzer = GeminiAnalyzer(api_key=config.gemini_api_key)
                if not analyzer.is_available():
                    logger.warning("AI 分析器初始化后不可用，请检查 API Key 配置")
                    analyzer = None
            else:
                logger.warning("未检测到 API Key (Gemini/OpenAI)，将仅使用模板生成报告")

            run_market_review(
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify,
                override_region=effective_region,
            )
            return 0

        # 模式2: 定时任务模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定时任务")
            logger.info(f"每日执行时间: {config.schedule_time}")

            # Determine whether to run immediately:
            # Command line arg --no-run-immediately overrides config if present.
            # Otherwise use config (defaults to True).
            should_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                should_run_immediately = False

            logger.info(f"启动时立即执行: {should_run_immediately}")

            from src.scheduler import run_with_schedule

            def scheduled_task():
                run_full_analysis(config, args, stock_codes)

            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=should_run_immediately
            )
            return 0

        # 模式3: 正常单次运行
        if config.run_immediately:
            run_full_analysis(config, args, stock_codes)
        else:
            logger.info("配置为不立即运行分析 (RUN_IMMEDIATELY=false)")

        logger.info("\n程序执行完成")

        # 如果启用了服务且是非定时任务模式，保持程序运行
        keep_running = start_serve and not (args.schedule or config.schedule_enabled)
        if keep_running:
            logger.info("API 服务运行中 (按 Ctrl+C 退出)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0

    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")
        return 130

    except Exception as e:
        logger.exception(f"程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
