# CLI Tool Support Analysis - main.py --tool 参数实现方案

## 文档目的

分析通过 `main.py --tool` 参数实现所有 Agent Tools 命令行调用的完整方案，明确：
1. 当前 CLI 能力现状
2. 需要新增的参数和功能
3. 哪些能力目前无法通过命令行实现
4. 实施步骤和优先级

## 1. 当前 CLI 能力盘点

### 1.1 已有命令行模式

| 参数 | 功能 | 对应能力 |
|------|------|---------|
| `--stocks CODE` | 分析指定股票 | 完整分析流程（含 AI） |
| `--market-review` | 大盘复盘 | 市场分析 + AI 总结 |
| `--backtest` | 回测评估 | 历史分析结果回测 |
| `--dry-run` | 仅获取数据 | 数据获取（无 AI 分析） |
| `--serve-only` | 启动 API 服务 | HTTP 接口服务 |
| `--webui` | 启动 Web UI | Web 界面 |

### 1.2 当前 CLI 的局限性

**无法直接调用单个工具**：
- 无法单独获取实时行情（必须走完整分析流程）
- 无法单独计算均线（必须走完整分析流程）
- 无法单独搜索新闻（必须通过 Agent 对话）
- 无法单独获取筹码分布（必须走完整分析流程）

**无法输出结构化数据**：
- 当前输出主要是日志和 Markdown 报告
- 无法输出 JSON 格式供其他程序调用
- 无法作为子进程被任务队列调用

## 2. Agent Tools 完整清单

### 2.1 数据工具 (5个)

| 工具名 | 功能 | 必需参数 | 可选参数 | 当前 CLI 支持 |
|--------|------|----------|----------|--------------|
| `get_realtime_quote` | 实时行情 | `stock_code` | - | ❌ 无 |
| `get_daily_history` | 历史K线 | `stock_code` | `days` (默认60) | ❌ 无 |
| `get_chip_distribution` | 筹码分布 | `stock_code` | - | ❌ 无 |
| `get_analysis_context` | 分析上下文 | `stock_code` | - | ❌ 无 |
| `get_stock_info` | 股票基本面 | `stock_code` | - | ❌ 无 |

### 2.2 分析工具 (4个)

| 工具名 | 功能 | 必需参数 | 可选参数 | 当前 CLI 支持 |
|--------|------|----------|----------|--------------|
| `analyze_trend` | 技术趋势分析 | `stock_code` | - | ❌ 无 |
| `calculate_ma` | 计算均线 | `stock_code` | `periods`, `days` | ❌ 无 |
| `get_volume_analysis` | 量能分析 | `stock_code` | `days` (默认30) | ❌ 无 |
| `analyze_pattern` | 形态识别 | `stock_code` | `days` (默认60) | ❌ 无 |

### 2.3 市场工具 (2个)

| 工具名 | 功能 | 必需参数 | 可选参数 | 当前 CLI 支持 |
|--------|------|----------|----------|--------------|
| `get_market_indices` | 市场指数 | - | `region` (默认cn) | ❌ 无 |
| `get_sector_rankings` | 板块排名 | - | `top_n` (默认10) | ❌ 无 |

### 2.4 搜索工具 (2个)

| 工具名 | 功能 | 必需参数 | 可选参数 | 当前 CLI 支持 |
|--------|------|----------|----------|--------------|
| `search_stock_news` | 搜索股票新闻 | `stock_code`, `stock_name` | `max_results` | ❌ 无 |
| `search_comprehensive_intel` | 综合情报搜索 | `stock_code`, `stock_name` | `max_searches` | ❌ 无 |

**总计**：13 个工具，当前 CLI 均不支持直接调用

## 3. 实施方案：融合到现有参数体系

### 3.1 设计原则

**问题**：当前参数已经很多（20+ 个），再新增 `--tool` 及相关参数会导致：
- 参数过多，用户难以记忆
- 参数冲突风险增加
- 帮助信息过长

**--dry-run 原始含义**：
- 仅获取数据并保存到数据库
- 跳过 AI 分析和报告生成
- 不发送通知

**语义冲突分析**：
- `--dry-run` 原意是"仅数据获取，不分析"
- 工具调用是"执行特定分析工具"
- 两者语义有冲突，不适合融合

### 3.2 方案对比

#### 方案 A：新增 --tool 参数（简洁方案）✅ 推荐
```bash
python main.py --tool quote --stocks 600519
python main.py --tool ma --stocks 600519 --periods 5,10,20
python main.py --tool indices --region cn
```
- ✅ 语义清晰：tool = 执行工具
- ✅ 复用现有 --stocks 参数
- ✅ 不破坏 --dry-run 原有语义
- ⚠️ 新增 1 个核心参数 + 5 个辅助参数
- ✅ 参数总数可控（26 个）

#### 方案 B：扩展 --dry-run 参数（语义冲突）❌ 不推荐
```bash
python main.py --dry-run quote --stocks 600519
```
- ❌ 语义冲突：dry-run = 不分析，但工具调用 = 执行分析
- ❌ 用户困惑：为什么"不分析"模式下还能执行分析工具？
- ✅ 参数数量少

#### 方案 C：使用子命令（最优雅但改动大）
```bash
python main.py tool quote 600519
python main.py tool ma 600519 --periods 5,10,20
python main.py analyze --stocks 600519
```
- ✅ 最清晰的语义
- ❌ 需要重构整个参数解析逻辑（使用 subparsers）
- ❌ 破坏现有用户习惯
- ❌ 实施时间长（16h+）

### 3.3 推荐方案：新增 --tool 参数（方案 A）

**选择理由**：
1. 语义清晰，不产生混淆
2. 保持 --dry-run 原有含义不变
3. 实施简单，风险可控
4. 参数数量增加可接受（6 个）

#### 参数设计

```python
# 1. 新增核心参数
parser.add_argument(
    '--tool',
    type=str,
    choices=[
        # Data tools (short names)
        'quote', 'history', 'chip', 'context', 'info',
        # Analysis tools (short names)
        'trend', 'ma', 'volume', 'pattern',
        # Market tools (short names)
        'indices', 'sectors',
        # Search tools (short names)
        'news', 'intel',
    ],
    help='Execute a single agent tool'
)

# 2. 复用现有 --stocks 参数（无需修改）
# Already exists: parser.add_argument('--stocks', type=str, help='Stock codes, comma separated')

# 3. 新增辅助参数
parser.add_argument(
    '--name',
    type=str,
    help='Stock name (for search tools)'
)

parser.add_argument(
    '--region',
    type=str,
    choices=['cn', 'us'],
    default='cn',
    help='Market region (for market indices)'
)

parser.add_argument(
    '--periods',
    type=str,
    help='MA periods, comma separated, e.g., "5,10,20,60" (for MA calculation)'
)

parser.add_argument(
    '--days',
    type=int,
    help='Number of days (for history, volume, pattern analysis)'
)

parser.add_argument(
    '--top-n',
    type=int,
    default=10,
    help='Number of results (for sector rankings)'
)

parser.add_argument(
    '--output-format',
    type=str,
    choices=['json', 'text', 'table'],
    default='json',
    help='Output format (default: json)'
)
```

**工具名称映射**：

```python
# Short alias -> Full tool name
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
```

**参数统计**：
- 新增核心参数：1 个（--tool）
- 新增辅助参数：6 个（--name, --region, --periods, --days, --top-n, --output-format）
- 复用参数：1 个（--stocks）
- 总计新增：7 个
- 参数总数：27 个（20 + 7）

### 3.4 需要新增的命令行参数

```python
# 在 parse_arguments() 中新增：

# 1. 核心参数
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
    help='Execute a single agent tool'
)

# 2. 复用现有 --stocks 参数（无需修改）
# Already exists

# 3. 新增辅助参数
parser.add_argument(
    '--name',
    type=str,
    help='Stock name (for search tools)'
)

parser.add_argument(
    '--region',
    type=str,
    choices=['cn', 'us'],
    default='cn',
    help='Market region (for market indices)'
)

parser.add_argument(
    '--periods',
    type=str,
    help='MA periods, comma separated, e.g., "5,10,20,60"'
)

parser.add_argument(
    '--days',
    type=int,
    help='Number of days (for history, volume, pattern)'
)

parser.add_argument(
    '--top-n',
    type=int,
    default=10,
    help='Number of results (for sector rankings)'
)

parser.add_argument(
    '--output-format',
    type=str,
    choices=['json', 'text', 'table'],
    default='json',
    help='Output format (default: json)'
)
```

### 3.5 execute_single_tool 函数实现

```python
# 工具别名映射
TOOL_ALIASES = {
    # 数据工具
    'quote': 'get_realtime_quote',
    'history': 'get_daily_history',
    'chip': 'get_chip_distribution',
    'context': 'get_analysis_context',
    'info': 'get_stock_info',
    # 分析工具
    'trend': 'analyze_trend',
    'ma': 'calculate_ma',
    'volume': 'get_volume_analysis',
    'pattern': 'analyze_pattern',
    # 市场工具
    'indices': 'get_market_indices',
    'sectors': 'get_sector_rankings',
    # 搜索工具
    'news': 'search_stock_news',
    'intel': 'search_comprehensive_intel',
    # 特殊值
    'data': None,  # 原有 dry-run 行为
}


def execute_single_tool(tool_alias: str, args: argparse.Namespace) -> Dict[str, Any]:
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
    if tool_name is None and tool_alias != 'data':
        return {"error": f"Unknown tool alias: {tool_alias}"}
    
    # Get stock code from --stocks parameter (support single code only for tools)
    stock_code = None
    if args.stocks:
        stock_code = args.stocks.split(',')[0].strip()
    
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
```

### 3.6 main() 函数集成

```python
def main() -> int:
    """Main function"""
    args = parse_arguments()
    
    # ... existing log configuration ...
    
    # ============================================================
    # Mode 0: Single Tool Execution (NEW)
    # ============================================================
    if args.tool:
        logger.info(f"Mode: Single tool execution ({args.tool})")
        
        # Execute tool
        result = execute_single_tool(args.tool, args)
        
        # Output result
        output_format = getattr(args, 'output_format', 'json')
        
        if output_format == "json":
            import json
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif output_format == "text":
            # Simple text format
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                for key, value in result.items():
                    print(f"{key}: {value}")
        elif output_format == "table":
            # Table format (use tabulate or simple implementation)
            try:
                from tabulate import tabulate
                if isinstance(result, dict) and not result.get("error"):
                    print(tabulate(result.items(), headers=["Field", "Value"], tablefmt="grid"))
                else:
                    print(result)
            except ImportError:
                # Fallback to text format
                for key, value in result.items():
                    print(f"{key}: {value}")
        
        return 0 if "error" not in result else 1
    
    # ============================================================
    # Mode 1: Original dry-run behavior (UNCHANGED)
    # ============================================================
    if args.dry_run:
        logger.info("Mode: Dry-run (data only, no AI analysis)")
        # ... existing dry-run logic ...
    
    # ... existing other modes ...
```

## 4. 使用示例

### 4.1 数据工具示例

```bash
# Get real-time quote
python main.py --tool quote --stocks 600519

# Get historical K-line data (last 120 days)
python main.py --tool history --stocks 600519 --days 120

# Get chip distribution
python main.py --tool chip --stocks 600519

# Get analysis context
python main.py --tool context --stocks 600519

# Get stock fundamental info
python main.py --tool info --stocks 600519
```

### 4.2 分析工具示例

```bash
# Technical trend analysis
python main.py --tool trend --stocks 600519

# Calculate MA (custom periods)
python main.py --tool ma --stocks 600519 --periods 5,10,20,60 --days 120

# Volume analysis (last 30 days)
python main.py --tool volume --stocks 600519 --days 30

# Pattern recognition (last 60 days)
python main.py --tool pattern --stocks 600519 --days 60
```

### 4.3 市场工具示例

```bash
# Get market indices (A-share)
python main.py --tool indices --region cn

# Get market indices (US)
python main.py --tool indices --region us

# Get sector rankings (top 10)
python main.py --tool sectors --top-n 10
```

### 4.4 搜索工具示例

```bash
# Search stock news
python main.py --tool news --stocks 600519 --name 贵州茅台

# Comprehensive intelligence search
python main.py --tool intel --stocks 600519 --name 贵州茅台
```

### 4.5 输出格式示例

```bash
# JSON format (default, suitable for programmatic use)
python main.py --tool quote --stocks 600519 --output-format json

# Text format (human-readable)
python main.py --tool quote --stocks 600519 --output-format text

# Table format (terminal-friendly)
python main.py --tool quote --stocks 600519 --output-format table
```

### 4.6 与现有功能对比

```bash
# Full analysis pipeline (existing, unchanged)
python main.py --stocks 600519              # Full AI analysis + report generation

# Data only (existing --dry-run, unchanged)
python main.py --dry-run --stocks 600519   # Fetch data only, no AI analysis

# Single tool call (NEW)
python main.py --tool quote --stocks 600519  # Get real-time quote only
```

## 5. 当前无法实现的能力

### 5.1 完全无法实现的功能

**无**：所有 13 个 Agent Tools 都可以通过 CLI 实现

### 5.2 需要额外工作的功能

1. **Agent 对话能力**
   - 当前方案：仅支持单工具调用
   - 无法实现：多轮对话、上下文记忆、工具链式调用
   - 解决方案：需要单独实现 `--chat` 模式（已有 API 接口）

2. **完整分析流程**
   - 当前方案：单工具调用
   - 无法实现：自动选择工具、AI 决策、生成报告
   - 解决方案：保留现有 `--stocks` 参数（已实现）

3. **异步任务管理**
   - 当前方案：同步执行，立即返回结果
   - 无法实现：任务队列、进度查询、结果缓存
   - 解决方案：通过 HTTP API 实现（已有接口）

## 6. 与任务队列的集成

### 6.1 任务队列调用方式

```python
# 在 task_queue.py 中构建命令
def _build_command(self, task_type: str, params: Dict[str, Any]) -> List[str]:
    """Build subprocess command line"""
    cmd = ["python", "main.py", "--no-notify", "--output-format", "json"]
    
    if task_type == "analyze":
        # Full analysis pipeline
        cmd.extend(["--stocks", params["stock_code"]])
    
    elif task_type == "trend":
        # Single tool: technical trend analysis
        cmd.extend(["--tool", "trend", "--stocks", params["stock_code"]])
    
    elif task_type == "ma":
        # Single tool: MA calculation
        cmd.extend(["--tool", "ma", "--stocks", params["stock_code"]])
        if params.get("periods"):
            cmd.extend(["--periods", params["periods"]])
        if params.get("days"):
            cmd.extend(["--days", str(params["days"])])
    
    elif task_type == "volume":
        # Single tool: volume analysis
        cmd.extend(["--tool", "volume", "--stocks", params["stock_code"]])
        if params.get("days"):
            cmd.extend(["--days", str(params["days"])])
    
    elif task_type == "pattern":
        # Single tool: pattern recognition
        cmd.extend(["--tool", "pattern", "--stocks", params["stock_code"]])
        if params.get("days"):
            cmd.extend(["--days", str(params["days"])])
    
    elif task_type == "news":
        # Single tool: search news
        cmd.extend([
            "--tool", "news",
            "--stocks", params["stock_code"],
            "--name", params["stock_name"]
        ])
    
    elif task_type == "intel":
        # Single tool: comprehensive intel
        cmd.extend([
            "--tool", "intel",
            "--stocks", params["stock_code"],
            "--name", params["stock_name"]
        ])
    
    elif task_type == "market_review":
        # Market review
        cmd.append("--market-review")
    
    elif task_type == "backtest":
        # Backtest
        cmd.append("--backtest")
        if params.get("code"):
            cmd.extend(["--backtest-code", params["code"]])
    
    return cmd
```

### 6.2 结果解析

```python
def _parse_result(self, task_type: str, params: Dict, stdout: str) -> Dict:
    """从 stdout 解析 JSON 结果"""
    import json
    
    try:
        # 尝试解析 JSON 输出
        result = json.loads(stdout)
        return result
    except json.JSONDecodeError:
        # 如果不是 JSON，从数据库读取（用于完整分析流程）
        if task_type == "analyze":
            from src.storage import get_db
            db = get_db()
            records = db.get_analysis_history(code=params["stock_code"], limit=1)
            if records:
                record = records[0]
                return {
                    "stock_code": record.code,
                    "stock_name": record.name,
                    "sentiment_score": record.sentiment_score,
                    # ... 其他字段
                }
        return {"error": "Failed to parse result", "stdout": stdout}
```

## 7. 实施步骤

### 步骤 1: 新增命令行参数（1小时）
- 在 `parse_arguments()` 中添加 --tool 参数
- 新增 6 个辅助参数（--name, --region, --periods, --days, --top-n, --output-format）
- 添加参数验证逻辑

### 步骤 2: 实现 execute_single_tool 函数（2小时）
- 实现工具别名映射（TOOL_ALIASES）
- 实现 13 个工具的调用逻辑
- 实现参数验证和错误处理
- 实现输出格式化（JSON/text/table）

### 步骤 3: 集成到 main() 函数（1小时）
- 添加工具执行模式判断
- 保持原有 --dry-run 行为不变
- 实现输出格式选择
- 实现错误码返回

### 步骤 4: 测试验证（2小时）
- 测试所有 13 个工具
- 测试各种参数组合
- 测试原有 --dry-run 行为不受影响
- 测试错误处理

### 步骤 5: 更新文档（1小时）
- 更新 README.md
- 添加使用示例
- 更新 --help 输出

**总计**：约 7 小时（1 个工作日）

## 8. 优先级建议

### P0（核心数据工具）- 2小时
- `get_realtime_quote`
- `get_daily_history`
- `get_stock_info`

### P1（分析工具）- 2小时
- `analyze_trend`
- `calculate_ma`
- `get_volume_analysis`
- `analyze_pattern`

### P2（市场和搜索工具）- 2小时
- `get_market_indices`
- `get_sector_rankings`
- `search_stock_news`
- `search_comprehensive_intel`

### P3（其他数据工具）- 1小时
- `get_chip_distribution`
- `get_analysis_context`

## 9. 风险评估

### 低风险
- ✅ 所有工具函数已实现，仅需封装
- ✅ 不修改现有功能，仅新增模式
- ✅ 输出 JSON 格式，易于解析

### 中风险
- ⚠️ 参数验证需要完善（避免参数错误）
- ⚠️ 错误处理需要统一（确保返回格式一致）

### 可控风险
- ⚠️ 搜索工具依赖外部 API（需要配置 API key）
- ⚠️ 部分工具需要数据库数据（如 analyze_trend）

## 10. 后续扩展

### 10.1 批量执行
```bash
# 批量执行多个股票
python main.py --tool get_realtime_quote --stocks 600519,000001,000002
```

### 10.2 管道支持
```bash
# 输出到文件
python main.py --tool get_realtime_quote --stock 600519 > quote.json

# 管道传递
python main.py --tool get_realtime_quote --stock 600519 | jq '.price'
```

### 10.3 配置文件支持
```bash
# 从配置文件读取参数
python main.py --tool calculate_ma --config ma_config.json
```

## 11. 总结

### 方案选择：新增 --tool 参数

**选择理由**：
1. ✅ 语义清晰：tool = 执行工具，不产生混淆
2. ✅ 保持 --dry-run 原有含义（仅获取数据，不分析）
3. ✅ 实施简单，风险可控
4. ✅ 参数数量增加可接受（7 个）
5. ✅ 不破坏现有用户习惯

**为什么不融合到 --dry-run**：
- ❌ 语义冲突：dry-run = "不分析"，但工具调用 = "执行分析"
- ❌ 用户困惑：为什么"不分析"模式下还能执行分析工具？
- ❌ 违反最小惊讶原则

### 可以实现的能力
✅ 所有 13 个 Agent Tools 都可以通过 CLI 调用
✅ 支持 JSON/text/table 多种输出格式
✅ 支持任务队列 subprocess 调用
✅ 支持管道和重定向
✅ 保持 --dry-run 原有行为不变

### 当前无法实现的能力
❌ 无（所有工具都可以实现）

### 需要额外工作的能力
- Agent 多轮对话（需要单独实现 --chat 模式）
- 异步任务管理（通过 HTTP API 实现）
- 完整分析流程（已有 --stocks 参数）

### 实施建议
1. 采用新增 --tool 参数方案
2. 优先实现 P0 核心数据工具（2小时）
3. 然后实现 P1 分析工具（2小时）
4. 最后实现 P2 市场和搜索工具（2小时）
5. 总计约 7 小时完成

### 下一步行动
1. 实施步骤 1-3（新增参数、实现函数、集成 main）
2. 进行测试验证
3. 更新文档和示例
