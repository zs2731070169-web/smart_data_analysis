"""
回归测试 CLI

遍历 build_test_suite1 / build_test_suite2 中的自然语言用例，依次驱动 LangGraph
流水线跑到终止状态，统计每条用例的：
  - is_relevant 是否为 True
  - 是否生成 HQL
  - validate 是否通过（即未触达 MAX_CORRECT_LOOPS）
  - 是否抛出异常
最终打印逐条结果与总体通过率。

用法（在项目根目录）：
  uv run python src/cli/regression_cli.py            # 默认跑 suite1
  uv run python src/cli/regression_cli.py --suite 2  # 跑 suite2
  uv run python src/cli/regression_cli.py --suite all
  uv run python src/cli/regression_cli.py --limit 5  # 仅跑前 5 条用于冒烟
"""
import argparse
import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agent.graph import MAX_CORRECT_LOOPS, graph
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import InputState
from infra.factory.repository_factory import repository_factory
from infra.log import task_id_context
from infra.log.logging import logger
from infra.manager.embedding_manager import embedding_manager


# ─────────────────────────────────────────────────────────────────────
# 基准测试：20 条用例，统计多维度质量指标
# ─────────────────────────────────────────────────────────────────────

def build_test_suite1() -> list[str]:
    """
    构建 20 条基准测试用例。
    维度覆盖：前年时间、YTD、日均指标(DAR/DAO)、年龄段、购买频次、
    新老客、品牌×地区、品牌跨年同比、性别×品类、会员×品类、
    性别×会员多维交叉、近6月×地区、地区×复购趋势、季度×地区×Top-N、历史年×地区×Top-N
    """
    return [
        # 前年 & YTD（2 条）
        "查询前年的总订单数和总销量",  # 前年，无维度
        "查询今年年初至今的总销售额和购买客户数",  # YTD，GMV + CUSTOMER_COUNT

        # 日均指标（2 条）
        "统计去年各大区的日均销售额",  # DAR by region
        "计算去年各月的日均订单数并找出订单量最低的月份",  # DAO by month + 排序

        # 月度客单价 & 省份趋势 & 性别×地区（3 条）
        "查询近12个月客单价最高和最低的月份",  # RPC by month，极值
        "统计各省份近12个月的销售额趋势，找出增幅最大的省份",  # PROVINCE_GMV，近N个月 + 排序
        "对比男女客户在华东地区的购买频次和销售额",  # PF + GMV，性别 × 地区

        # 购买频次 & 新老客（2 条）
        "对比不同会员等级的购买频次和日均订单数",  # PF + DAO by member_level
        "查询新客户和复购客户在各大区的销售额分布",  # GMV by region + 新老客

        # 品牌 × 地区 / 跨年同比（3 条）
        "查询去年各品牌在不同大区的销售额排名",  # BRAND_REGION_GMV
        "对比各品牌去年和前年的销售额变化",  # BRAND_GMV，跨年同比
        "查询华南地区销售额最高的品牌及其订单数",  # BRAND_GMV + BRAND_ORDERS，地区过滤

        # 性别 × 品类 / 会员 × 品类（2 条）
        "统计男女客户在各品类的销售额分布",  # GENDER_CATEGORY_GMV
        "对比去年各会员等级在不同品类的客单价",  # RPC by member_level + category

        # 多维交叉（1 条）
        "统计去年男女客户在各会员等级的分布及各自客单价",  # MEMBER + GENDER 多维

        # 地区 × 近N月 / 复购趋势（2 条）
        "统计近6个月华东地区各月的销售额和订单数",  # MONTHLY_GMV + MONTHLY_ORDERS，地区
        "统计近12个月华北地区各月复购客户数的变化",  # REPURCHASE_COUNT by month，地区

        # 季度 × 地区 × Top-N / 历史年 × 地区 × Top-N（2 条）
        "统计今年Q1华南地区销量前5的商品品类",  # CATEGORY_QTY，季度 + 地区 + Top-N
        "查询2024年各大区销售额最高的前3个品类",  # CATEGORY_GMV by region，历史年 + 地区 + Top-N
    ]


def build_test_suite2() -> list[str]:
    return [
        # ── 基础汇总 ──────────────────────────────────────────────────
        "查询去年的总销售额和总订单数",  # GMV + ORDER_COUNT，无维度过滤
        "统计去年的总销量和件单价",  # TOTAL_QTY + ASP
        "查询今年年初至今的总销售额",  # GMV，YTD 单指标
        "统计去年的总购买客户数",  # CUSTOMER_COUNT，无维度
        "查询前年的总订单数和总销量",  # ORDER_COUNT + TOTAL_QTY，前年
        "计算去年的整体客单价",  # RPC，全年单值
        "统计去年的日均销售额",  # DAR，全年均值
        "查询今年年初至今的总订单数和购买客户数",  # ORDER_COUNT + CUSTOMER_COUNT，YTD
        "统计去年的总复购客户数和复购率",  # REPURCHASE_COUNT + RPR，无维度
        "查询2024年的总销售额、总订单数和件单价",  # GMV + ORDER_COUNT + ASP，历史年三指标
        "计算今年年初至今的日均订单数",  # DAO，YTD 单值
        "统计去年的总销量和购买客户数",  # TOTAL_QTY + CUSTOMER_COUNT，无维度

        # ── 时间维度 ──────────────────────────────────────────────────
        "查询近12个月每月的销售额变化趋势",  # MONTHLY_GMV，按月分组
        "对比今年第一季度和第二季度的销售额及订单数",  # QUARTERLY_GMV + QUARTERLY_ORDERS，进行中季度
        "统计去年每个季度的销量",  # QUARTERLY_QTY，按季度分组
        "计算今年各月的日均订单数",  # DAO，按月分组
        "查询近3个月每月的销售额和订单数",  # MONTHLY_GMV + MONTHLY_ORDERS，近N个月（不含当月）
        "统计2024年全年各月的销量趋势",  # MONTHLY_QTY，历史完整年按月分组
        "查询今年年初至今的总销售额和购买客户数",  # GMV + CUSTOMER_COUNT，YTD（1月1日至今天）
        "对比去年第一季度和今年第一季度的销售额",  # QUARTERLY_GMV，同比跨年季度对比
        "统计去年下半年（第三、四季度）的总订单数和总销量",  # ORDER_COUNT + TOTAL_QTY，去年指定多季度
        "查询近6个月日均销售额最高的前3个月",  # DAR，近N个月 + 日均 + Top-N
        "计算2024年每个季度的客单价（RPC）变化",  # RPC，历史年按季度分组
        "统计今年1月和2月的销售额及环比上月变化",  # MONTHLY_GMV，本年指定月份 + 环比（用子查询）
        "查询前年（2024年）销售额最高的月份及其销售额",  # MONTHLY_GMV，前年 + Top-1
        "计算去年各月的日均订单数并找出订单量最低的月份",  # DAO，去年按月分组 + 排序
        "统计去年上半年各月的销售额及购买客户数",  # MONTHLY_GMV + MONTHLY_CUSTOMERS，去年上半年
        "对比今年Q1与去年Q1的订单数和销量",  # QUARTERLY_ORDERS + QUARTERLY_QTY，同比
        "查询近9个月每月的日均销售额",  # DAR，近N个月按月分组
        "统计2024年第二季度每月的件单价变化",  # ASP by month，历史年指定季度
        "查询近6个月中销售额环比增幅最大的月份",  # MONTHLY_GMV，近N个月 + 环比计算 + Top-1
        "计算去年第四季度和今年第一季度的销售额对比",  # QUARTERLY_GMV，跨年相邻季度对比
        "统计今年1至3月每月的复购客户数",  # MONTHLY_REPURCHASE_COUNT，本年指定月份
        "查询近12个月客单价最高和最低的月份",  # RPC by month，近N个月 + 极值
        "对比去年各季度的购买客户数和复购率",  # QUARTERLY_CUSTOMERS + RPR，去年按季度
        "统计今年年初至今各月的累计销售额",  # MONTHLY_GMV，YTD 按月分组

        # ── 商品 / 品类 / 品牌 ───────────────────────────────────────
        "查询销售额最高的前5个商品品类",  # CATEGORY_GMV，Top-N
        "统计各品牌的销量，列出销量前3的品牌",  # BRAND_QTY，Top-N
        "查询件单价最高的前10款商品",  # ASP by product，Top-N
        "统计去年销量最高的前10款商品",  # PRODUCT_QTY，时间过滤 + Top-N
        "查询各品类的购买客户数排名",  # CATEGORY_CUSTOMERS
        "对比各品牌的客单价",  # BRAND_RPC，多品牌对比
        "查询去年各品类的销售额及占比",  # CATEGORY_GMV + 占比，去年
        "统计去年销量最低的10款商品",  # PRODUCT_QTY，时间过滤 + Bottom-N
        "查询各品牌的订单数和购买客户数排名",  # BRAND_ORDERS + BRAND_CUSTOMERS
        "统计各品类的复购率并找出复购率最高的品类",  # RPR by category，Top-1
        "对比去年各品牌的日均销售额",  # DAR by brand，去年
        "查询今年年初至今件单价最高的前5款商品",  # ASP by product，YTD + Top-N
        "统计各品类中客单价最高的品类及其销售额",  # RPC + GMV by category，Top-1
        "查询2024年销量前10品牌中各品牌的订单数",  # BRAND_QTY + BRAND_ORDERS，历史年 + Top-N
        "对比各品牌去年和前年的销售额变化",  # BRAND_GMV，同比跨年
        "统计各品类的件单价并找出件单价低于整体均值的品类",  # ASP by category + HAVING 过滤

        # ── 地区维度 ──────────────────────────────────────────────────
        "统计华东地区各省份的销售额排名",  # PROVINCE_GMV，大区过滤
        "对比华东、华南、华北三个大区的销售额和客户数",  # REGION_GMV + REGION_CUSTOMERS
        "查询各省份的订单数，找出订单量最多的前5个省份",  # PROVINCE_ORDERS，Top-N
        "统计去年各大区的销售额及订单数",  # REGION_GMV + REGION_ORDERS，去年
        "查询华南地区去年销量最高的前3个省份",  # PROVINCE_QTY，大区过滤 + 时间 + Top-N
        "对比各大区今年Q1和Q2的销售额变化",  # REGION_GMV，大区 + 季度对比
        "统计华东各省份的购买客户数和复购率",  # PROVINCE_CUSTOMERS + RPR，大区过滤
        "查询各省份的件单价排名，找出件单价最高的5个省份",  # ASP by province，Top-N
        "统计去年各大区的日均销售额",  # DAR by region，去年
        "查询华北地区各省份的订单数及占华北总订单数的比例",  # PROVINCE_ORDERS + 占比，大区过滤
        "对比华南和华北地区去年的客单价",  # RPC by region，两区对比
        "统计各省份近12个月的销售额趋势，找出增幅最大的省份",  # PROVINCE_GMV，近N个月 + 排序
        "查询华东地区各省份去年的销量和件单价",  # PROVINCE_QTY + ASP，大区 + 时间

        # ── 客户行为 ──────────────────────────────────────────────────
        "统计各商品品类的复购客户数和复购率",  # REPURCHASE_COUNT + RPR by category
        "查询各会员等级的销售额、订单数和客单价",  # MEMBER_GMV + MEMBER_ORDERS + RPC
        "统计各会员等级的复购率和复购客户数",  # RPR + REPURCHASE_COUNT by member_level
        "查询购买频次最高的前10个客户的总销售额",  # PF + GMV by customer，Top-N
        "统计各会员等级去年的销量和件单价",  # MEMBER_QTY + ASP，去年 + 会员分组
        "查询去年复购率最高的3个商品品类",  # RPR by category，去年 + Top-N
        "统计近12个月各月新增购买客户数的趋势",  # NEW_CUSTOMER_COUNT by month，近N个月
        "对比不同会员等级的购买频次和日均订单数",  # PF + DAO by member_level
        "查询去年各会员等级的购买频次分布",  # PF by member_level，去年
        "统计各会员等级今年年初至今的销售额及客单价",  # MEMBER_GMV + RPC，YTD
        "查询购买客户数最多的前5个商品品类及其复购率",  # CATEGORY_CUSTOMERS + RPR，Top-N
        "对比高级会员与普通会员去年的销售额差异",  # MEMBER_GMV，会员等级对比

        # ── 人群对比 ──────────────────────────────────────────────────
        "对比男女客户的销售额、购买频次和客单价",  # GENDER_GMV + PF + RPC by gender
        "统计不同年龄段客户的销售额和订单数",  # AGE_GMV + AGE_ORDERS，年龄分组
        "对比去年男女客户的复购率和复购客户数",  # RPR + REPURCHASE_COUNT by gender，去年
        "查询各年龄段客户的件单价排名",  # ASP by age_group
        "统计男女客户在各品类的销售额分布",  # GENDER_CATEGORY_GMV，性别 + 品类
        "对比不同年龄段客户的购买频次和客单价",  # PF + RPC by age_group
        "查询去年男性和女性客户销量最高的前5款商品",  # PRODUCT_QTY by gender，去年 + Top-N
        "统计各年龄段客户近12个月的销售额趋势",  # AGE_GMV by month，近N个月 + 年龄分组
        "对比高消费人群（客单价前20%）与普通人群的购买频次",  # PF，客单价分层对比
        "查询新客户和复购客户在各大区的销售额分布",  # GMV by region + 新老客，地区 + 人群
        "统计去年男女客户在各会员等级的分布及各自客单价",  # MEMBER + GENDER，多维交叉

        # ── 多维组合 ──────────────────────────────────────────────────
        "查询华南地区销售额最高的品牌及其订单数",  # BRAND_GMV + BRAND_ORDERS，地区过滤
        "统计华东地区各品类去年的销售额和复购率",  # CATEGORY_GMV + RPR，地区 + 时间
        "查询去年各大区销量最高的品牌",  # BRAND_QTY by region，地区 + 时间 + Top-1
        "对比华南和华北地区各品类的客单价差异",  # RPC by category + region，两区对比
        "统计近6个月华东地区各月的销售额和订单数",  # MONTHLY_GMV + MONTHLY_ORDERS，地区 + 近N个月
        "查询去年各大区高级会员的销售额及客单价",  # REGION_GMV + RPC，地区 + 会员等级
        "统计今年Q1华南地区销量前5的商品品类",  # CATEGORY_QTY，季度 + 地区 + Top-N
        "对比男女客户在华东地区的购买频次和销售额",  # PF + GMV，性别 + 地区
        "查询去年各品牌在不同大区的销售额排名",  # BRAND_REGION_GMV，品牌 + 地区
        "统计近12个月华北地区各月复购客户数的变化",  # REPURCHASE_COUNT by month，地区 + 近N个月
        "查询2024年各大区销售额最高的前3个品类",  # CATEGORY_GMV by region，历史年 + 地区 + Top-N
        "对比去年各会员等级在不同品类的客单价",  # RPC by member_level + category，多维
    ]


@dataclass
class CaseResult:
    """单条用例的回归结果"""
    index: int
    question: str
    passed: bool
    reason: str
    elapsed_ms: int
    is_relevant: bool = False
    has_hql: bool = False
    correct_count: int = 0
    validate_passed: bool = False
    error: str = ""


def _judge(final_state: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """
    根据终止状态判定用例是否通过。
    通过条件（同时满足）：
      1. is_relevant == True
      2. 生成了非空 HQL
      3. correct_count < MAX_CORRECT_LOOPS（即未走到纠错回路上限）
    """
    is_relevant = bool(final_state.get("is_relevant"))
    hql = final_state.get("hql") or ""
    correct_count = final_state.get("correct_count", 0) or 0
    validates = final_state.get("validates") or []
    last_round_invalid = any(not v.is_valid for v in validates)
    validate_passed = (correct_count < MAX_CORRECT_LOOPS) and (not last_round_invalid)

    metrics = {
        "is_relevant": is_relevant,
        "has_hql": bool(hql.strip()),
        "correct_count": correct_count,
        "validate_passed": validate_passed,
    }

    if not is_relevant:
        return False, "意图判定为无关或需追问", metrics
    if not metrics["has_hql"]:
        return False, "未生成 HQL", metrics
    if not validate_passed:
        return False, f"校验未通过（correct_count={correct_count}）", metrics

    return True, "OK", metrics


async def _run_one(index: int, question: str, context: EnvContext) -> CaseResult:
    """跑单条用例，捕获任何异常并标记为失败"""
    task_id_context.set(uuid.uuid4().hex)
    start = time.perf_counter()
    try:
        final_state = await graph.ainvoke(
            input=InputState(question=question),
            context=context,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        passed, reason, metrics = _judge(final_state)
        return CaseResult(
            index=index,
            question=question,
            passed=passed,
            reason=reason,
            elapsed_ms=elapsed_ms,
            **metrics,
        )
    except Exception as e:  # noqa: BLE001 - 回归脚本需要捕获所有异常以保证遍历完所有用例
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(f"[{index}] 用例执行抛出异常: {question}")
        return CaseResult(
            index=index,
            question=question,
            passed=False,
            reason=f"异常：{type(e).__name__}",
            elapsed_ms=elapsed_ms,
            error=str(e),
        )


def _print_report(results: list[CaseResult]) -> None:
    """打印逐条结果与汇总"""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total else 0.0
    avg_ms = (sum(r.elapsed_ms for r in results) / total) if total else 0

    print("\n" + "=" * 100)
    print(f"{'#':<4}{'通过':<6}{'耗时(ms)':<10}{'相关':<6}{'HQL':<6}{'纠错':<6}问题 / 失败原因")
    print("-" * 100)
    for r in results:
        flag = "✅" if r.passed else "❌"
        rel = "Y" if r.is_relevant else "N"
        hql = "Y" if r.has_hql else "N"
        tail = r.question if r.passed else f"{r.question}  →  {r.reason}"
        print(f"{r.index:<4}{flag:<6}{r.elapsed_ms:<10}{rel:<6}{hql:<6}{r.correct_count:<6}{tail}")
    print("=" * 100)
    print(f"总计 {total}  通过 {passed}  失败 {failed}  通过率 {pass_rate:.1f}%  平均耗时 {avg_ms:.0f}ms")
    print("=" * 100 + "\n")


def _select_suite(suite_name: str) -> list[str]:
    if suite_name == "1":
        return build_test_suite1()
    if suite_name == "2":
        return build_test_suite2()
    if suite_name == "all":
        return build_test_suite1() + build_test_suite2()
    raise ValueError(f"未知 suite: {suite_name}（支持 1 / 2 / all）")


async def run_regression(suite_name: str, limit: int | None) -> int:
    """
    主入口：构建用例集 → 初始化连接 → 顺序执行 → 打印报告。
    返回失败用例数（>0 表示有回归）。
    """
    cases = _select_suite(suite_name)
    if limit and limit > 0:
        cases = cases[:limit]
    if not cases:
        logger.warning(f"suite={suite_name} 当前为空，无可执行用例")
        return 0

    logger.info(f"准备执行回归 suite={suite_name}，共 {len(cases)} 条用例")

    async with repository_factory as repos:
        context: EnvContext = EnvContext(
            repositories=repos,
            embedding_client=embedding_manager.embedding_client,
        )
        results: list[CaseResult] = []
        for idx, question in enumerate(cases, start=1):
            logger.info(f"[{idx}/{len(cases)}] 执行用例: {question}")
            result = await _run_one(idx, question, context)
            status = "PASS" if result.passed else "FAIL"
            logger.info(
                f"[{idx}/{len(cases)}] {status} | {result.elapsed_ms}ms | reason={result.reason}"
            )
            results.append(result)

    _print_report(results)
    return sum(1 for r in results if not r.passed)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangGraph 流水线回归测试")
    parser.add_argument(
        "--suite",
        default="1",
        choices=["1", "2", "all"],
        help="用例集合：1=suite1（默认）；2=suite2；all=两者合并",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅执行前 N 条用例，便于冒烟测试",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    failed_count = asyncio.run(run_regression(args.suite, args.limit))
    raise SystemExit(0 if failed_count == 0 else 1)
