import uuid

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from agent.node.analyze_result_node import analyze_result_node
from agent.node.clarify_node import clarify_node
from agent.node.column_retrieval_node import column_retrieval_node
from agent.node.correct_hql_node import correct_hql_node
from agent.node.entity_extract_node import entity_extract_node
from agent.node.execute_hql_node import execute_hql_node
from agent.node.expand_node import expand_node
from agent.node.fallback_node import fallback_node
from agent.node.generate_hql_node import generate_hql_node
from agent.node.intent_check_node import intent_check_node
from agent.node.merge_node import merge_node
from agent.node.metric_filter_node import metric_filter_node
from agent.node.metrics_retrieval_node import metrics_retrieval_node
from agent.node.missing_complete_node import missing_complete_node
from agent.node.table_filter_node import table_filter_node
from agent.node.validate_hql_node import validate_hql_node
from agent.node.value_retrieval_node import value_retrieval_node
from agent.schema.context_schema import EnvContext
from agent.schema.state_schema import OverallState, InputState
from conf.app_config import MAX_UNFOUND_COUNT, MAX_CORRECT_COUNT
from infra.factory.repository_factory import repository_factory
from infra.log import task_id_context
from infra.manager.embedding_manager import embedding_manager

# 创建图
builder = StateGraph(
    input_schema=InputState,
    state_schema=OverallState,
    context_schema=EnvContext)

builder.add_node(node="intent_check_node", action=intent_check_node)
builder.add_node(node="clarify_node", action=clarify_node)
builder.add_node(node="entity_extract_node", action=entity_extract_node)
builder.add_node(node="column_retrieval_node", action=column_retrieval_node)
builder.add_node(node="metrics_retrieval_node", action=metrics_retrieval_node)
builder.add_node(node="value_retrieval_node", action=value_retrieval_node)
builder.add_node(node="merge_node", action=merge_node)
builder.add_node(node="table_filter_node", action=table_filter_node)
builder.add_node(node="metric_filter_node", action=metric_filter_node)
builder.add_node(node="expand_node", action=expand_node)
builder.add_node(node="generate_hql_node", action=generate_hql_node)
builder.add_node(node="validate_hql_node", action=validate_hql_node)
builder.add_node(node="missing_complete_node", action=missing_complete_node)
builder.add_node(node="correct_hql_node", action=correct_hql_node)
builder.add_node(node="execute_hql_node", action=execute_hql_node)
builder.add_node(node="analyze_result_node", action=analyze_result_node)
builder.add_node(node="fallback_node", action=fallback_node)

builder.add_edge(start_key=START, end_key="intent_check_node")
builder.add_conditional_edges(
    source="intent_check_node",
    path=lambda state: (
        "clarify" if state.get("clarification_question")
        else "entity_extract" if state.get("is_relevant")
        else "fallback"
    ),
    path_map={
        "clarify": "clarify_node",
        "entity_extract": "entity_extract_node",
        "fallback": "fallback_node",
    },
)
builder.add_edge(start_key="entity_extract_node", end_key="column_retrieval_node")
builder.add_edge(start_key="entity_extract_node", end_key="metrics_retrieval_node")
builder.add_edge(start_key="entity_extract_node", end_key="value_retrieval_node")
builder.add_edge(
    start_key=["column_retrieval_node", "metrics_retrieval_node", "value_retrieval_node"],
    end_key="merge_node")
builder.add_edge(start_key="merge_node", end_key="table_filter_node")
builder.add_edge(start_key="merge_node", end_key="metric_filter_node")
builder.add_edge(start_key=["table_filter_node", "metric_filter_node"], end_key="expand_node")
builder.add_edge(start_key="expand_node", end_key="generate_hql_node")
# generate_hql_node 判定数据表无法满足问题时，直接跳 fallback，避免无意义的校验/纠错循环
builder.add_conditional_edges(
    source="generate_hql_node",
    path=lambda state: "fallback" if state.get("unable_to_answer_advice") else "validate_hql",
    path_map={"validate_hql": "validate_hql_node", "fallback": "fallback_node"},
)
# 如果校验结果为空就执行hql，如果校验结果不为空但纠错轮次未达上限就进入补全节点，如果校验结果不为空且纠错轮次已达上限就进入兜底节点
builder.add_conditional_edges(
    source="validate_hql_node",
    path=lambda state: (
        "execute_hql" if not state.get("validates")
        else "fallback" if state.get("correct_count", 0) >= MAX_CORRECT_COUNT
        else "missing_complete"
    ),
    path_map={
        "execute_hql": "execute_hql_node",
        "missing_complete": "missing_complete_node",
        "fallback": "fallback_node",
    }
)
# 查不到字段时继续尝试纠错，累计失败达 MAX_UNFOUND_COUNT 次后才触发降级
builder.add_conditional_edges(
    source="missing_complete_node",
    path=lambda state: "fallback" if state.get("unfound_count", 0) >= MAX_UNFOUND_COUNT else "correct_hql",
    path_map={"correct_hql": "correct_hql_node", "fallback": "fallback_node"}
)
builder.add_edge(start_key="correct_hql_node", end_key="validate_hql_node")
builder.add_conditional_edges(
    source="execute_hql_node",
    path=lambda state: "analyze_result" if state.get("execute_result") else "fallback",
    path_map={"analyze_result": "analyze_result_node", "fallback": "fallback_node"},
)
builder.add_edge(start_key="analyze_result_node", end_key=END)
builder.add_edge(start_key="fallback_node", end_key=END)

graph = builder.compile()


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
        # "查询去年的总销售额和总订单数",                   # GMV + ORDER_COUNT，无维度过滤
        # "统计去年的总销量和件单价",                       # TOTAL_QTY + ASP
        # "查询今年年初至今的总销售额",                     # GMV，YTD 单指标
        # "统计去年的总购买客户数",                         # CUSTOMER_COUNT，无维度
        # "查询前年的总订单数和总销量",                     # ORDER_COUNT + TOTAL_QTY，前年
        # "计算去年的整体客单价",                           # RPC，全年单值
        # "统计去年的日均销售额",                           # DAR，全年均值
        # "查询今年年初至今的总订单数和购买客户数",         # ORDER_COUNT + CUSTOMER_COUNT，YTD
        # "统计去年的总复购客户数和复购率",                 # REPURCHASE_COUNT + RPR，无维度
        # "查询2024年的总销售额、总订单数和件单价",         # GMV + ORDER_COUNT + ASP，历史年三指标
        # "计算今年年初至今的日均订单数",                   # DAO，YTD 单值
        # "统计去年的总销量和购买客户数",                   # TOTAL_QTY + CUSTOMER_COUNT，无维度
        #
        # # ── 时间维度 ──────────────────────────────────────────────────
        # "查询近12个月每月的销售额变化趋势",               # MONTHLY_GMV，按月分组
        # "对比今年第一季度和第二季度的销售额及订单数",      # QUARTERLY_GMV + QUARTERLY_ORDERS，进行中季度
        # "统计去年每个季度的销量",                         # QUARTERLY_QTY，按季度分组
        # "计算今年各月的日均订单数",                       # DAO，按月分组
        # "查询近3个月每月的销售额和订单数",                # MONTHLY_GMV + MONTHLY_ORDERS，近N个月（不含当月）
        # "统计2024年全年各月的销量趋势",                   # MONTHLY_QTY，历史完整年按月分组
        # "查询今年年初至今的总销售额和购买客户数",         # GMV + CUSTOMER_COUNT，YTD（1月1日至今天）
        # "对比去年第一季度和今年第一季度的销售额",         # QUARTERLY_GMV，同比跨年季度对比
        # "统计去年下半年（第三、四季度）的总订单数和总销量",  # ORDER_COUNT + TOTAL_QTY，去年指定多季度
        # "查询近6个月日均销售额最高的前3个月",             # DAR，近N个月 + 日均 + Top-N
        # "计算2024年每个季度的客单价（RPC）变化",          # RPC，历史年按季度分组
        # "统计今年1月和2月的销售额及环比上月变化",         # MONTHLY_GMV，本年指定月份 + 环比（用子查询）
        # "查询前年（2024年）销售额最高的月份及其销售额",   # MONTHLY_GMV，前年 + Top-1
        # "计算去年各月的日均订单数并找出订单量最低的月份", # DAO，去年按月分组 + 排序
        # "统计去年上半年各月的销售额及购买客户数",         # MONTHLY_GMV + MONTHLY_CUSTOMERS，去年上半年
        # "对比今年Q1与去年Q1的订单数和销量",              # QUARTERLY_ORDERS + QUARTERLY_QTY，同比
        # "查询近9个月每月的日均销售额",                    # DAR，近N个月按月分组
        # "统计2024年第二季度每月的件单价变化",             # ASP by month，历史年指定季度
        # "查询近6个月中销售额环比增幅最大的月份",          # MONTHLY_GMV，近N个月 + 环比计算 + Top-1
        # "计算去年第四季度和今年第一季度的销售额对比",     # QUARTERLY_GMV，跨年相邻季度对比
        # "统计今年1至3月每月的复购客户数",                 # MONTHLY_REPURCHASE_COUNT，本年指定月份
        # "查询近12个月客单价最高和最低的月份",             # RPC by month，近N个月 + 极值
        # "对比去年各季度的购买客户数和复购率",             # QUARTERLY_CUSTOMERS + RPR，去年按季度
        # "统计今年年初至今各月的累计销售额",               # MONTHLY_GMV，YTD 按月分组
        #
        # # ── 商品 / 品类 / 品牌 ───────────────────────────────────────
        # "查询销售额最高的前5个商品品类",                  # CATEGORY_GMV，Top-N
        # "统计各品牌的销量，列出销量前3的品牌",            # BRAND_QTY，Top-N
        # "查询件单价最高的前10款商品",                     # ASP by product，Top-N
        # "统计去年销量最高的前10款商品",                   # PRODUCT_QTY，时间过滤 + Top-N
        # "查询各品类的购买客户数排名",                     # CATEGORY_CUSTOMERS
        # "对比各品牌的客单价",                             # BRAND_RPC，多品牌对比
        # "查询去年各品类的销售额及占比",                   # CATEGORY_GMV + 占比，去年
        # "统计去年销量最低的10款商品",                     # PRODUCT_QTY，时间过滤 + Bottom-N
        # "查询各品牌的订单数和购买客户数排名",             # BRAND_ORDERS + BRAND_CUSTOMERS
        # "统计各品类的复购率并找出复购率最高的品类",        # RPR by category，Top-1
        # "对比去年各品牌的日均销售额",                     # DAR by brand，去年
        # "查询今年年初至今件单价最高的前5款商品",          # ASP by product，YTD + Top-N
        # "统计各品类中客单价最高的品类及其销售额",          # RPC + GMV by category，Top-1
        # "查询2024年销量前10品牌中各品牌的订单数",         # BRAND_QTY + BRAND_ORDERS，历史年 + Top-N
        # "对比各品牌去年和前年的销售额变化",               # BRAND_GMV，同比跨年
        # "统计各品类的件单价并找出件单价低于整体均值的品类", # ASP by category + HAVING 过滤
        #
        # # ── 地区维度 ──────────────────────────────────────────────────
        # "统计华东地区各省份的销售额排名",                 # PROVINCE_GMV，大区过滤
        # "对比华东、华南、华北三个大区的销售额和客户数",   # REGION_GMV + REGION_CUSTOMERS
        # "查询各省份的订单数，找出订单量最多的前5个省份",  # PROVINCE_ORDERS，Top-N
        # "统计去年各大区的销售额及订单数",                 # REGION_GMV + REGION_ORDERS，去年
        # "查询华南地区去年销量最高的前3个省份",            # PROVINCE_QTY，大区过滤 + 时间 + Top-N
        # "对比各大区今年Q1和Q2的销售额变化",              # REGION_GMV，大区 + 季度对比
        # "统计华东各省份的购买客户数和复购率",             # PROVINCE_CUSTOMERS + RPR，大区过滤
        # "查询各省份的件单价排名，找出件单价最高的5个省份", # ASP by province，Top-N
        # "统计去年各大区的日均销售额",                     # DAR by region，去年
        # "查询华北地区各省份的订单数及占华北总订单数的比例", # PROVINCE_ORDERS + 占比，大区过滤
        # "对比华南和华北地区去年的客单价",                 # RPC by region，两区对比
        # "统计各省份近12个月的销售额趋势，找出增幅最大的省份", # PROVINCE_GMV，近N个月 + 排序
        # "查询华东地区各省份去年的销量和件单价",           # PROVINCE_QTY + ASP，大区 + 时间
        #
        # # ── 客户行为 ──────────────────────────────────────────────────
        # "统计各商品品类的复购客户数和复购率",             # REPURCHASE_COUNT + RPR by category
        # "查询各会员等级的销售额、订单数和客单价",         # MEMBER_GMV + MEMBER_ORDERS + RPC
        # "统计各会员等级的复购率和复购客户数",             # RPR + REPURCHASE_COUNT by member_level
        # "查询购买频次最高的前10个客户的总销售额",         # PF + GMV by customer，Top-N
        # "统计各会员等级去年的销量和件单价",               # MEMBER_QTY + ASP，去年 + 会员分组
        # "查询去年复购率最高的3个商品品类",                # RPR by category，去年 + Top-N
        # "统计近12个月各月新增购买客户数的趋势",           # NEW_CUSTOMER_COUNT by month，近N个月
        # "对比不同会员等级的购买频次和日均订单数",         # PF + DAO by member_level
        # "查询去年各会员等级的购买频次分布",               # PF by member_level，去年
        # "统计各会员等级今年年初至今的销售额及客单价",     # MEMBER_GMV + RPC，YTD
        # "查询购买客户数最多的前5个商品品类及其复购率",    # CATEGORY_CUSTOMERS + RPR，Top-N
        # "对比高级会员与普通会员去年的销售额差异",         # MEMBER_GMV，会员等级对比
        #
        # # ── 人群对比 ──────────────────────────────────────────────────
        # "对比男女客户的销售额、购买频次和客单价",         # GENDER_GMV + PF + RPC by gender
        # "统计不同年龄段客户的销售额和订单数",             # AGE_GMV + AGE_ORDERS，年龄分组
        # "对比去年男女客户的复购率和复购客户数",           # RPR + REPURCHASE_COUNT by gender，去年
        # "查询各年龄段客户的件单价排名",                   # ASP by age_group
        # "统计男女客户在各品类的销售额分布",               # GENDER_CATEGORY_GMV，性别 + 品类
        # "对比不同年龄段客户的购买频次和客单价",           # PF + RPC by age_group
        # "查询去年男性和女性客户销量最高的前5款商品",      # PRODUCT_QTY by gender，去年 + Top-N
        # "统计各年龄段客户近12个月的销售额趋势",           # AGE_GMV by month，近N个月 + 年龄分组
        # "对比高消费人群（客单价前20%）与普通人群的购买频次", # PF，客单价分层对比
        # "查询新客户和复购客户在各大区的销售额分布",       # GMV by region + 新老客，地区 + 人群
        # "统计去年男女客户在各会员等级的分布及各自客单价", # MEMBER + GENDER，多维交叉
        #
        # # ── 多维组合 ──────────────────────────────────────────────────
        # "查询华南地区销售额最高的品牌及其订单数",         # BRAND_GMV + BRAND_ORDERS，地区过滤
        # "统计华东地区各品类去年的销售额和复购率",         # CATEGORY_GMV + RPR，地区 + 时间
        # "查询去年各大区销量最高的品牌",                   # BRAND_QTY by region，地区 + 时间 + Top-1
        # "对比华南和华北地区各品类的客单价差异",           # RPC by category + region，两区对比
        # "统计近6个月华东地区各月的销售额和订单数",        # MONTHLY_GMV + MONTHLY_ORDERS，地区 + 近N个月
        # "查询去年各大区高级会员的销售额及客单价",         # REGION_GMV + RPC，地区 + 会员等级
        # "统计今年Q1华南地区销量前5的商品品类",            # CATEGORY_QTY，季度 + 地区 + Top-N
        # "对比男女客户在华东地区的购买频次和销售额",       # PF + GMV，性别 + 地区
        # "查询去年各品牌在不同大区的销售额排名",           # BRAND_REGION_GMV，品牌 + 地区
        # "统计近12个月华北地区各月复购客户数的变化",       # REPURCHASE_COUNT by month，地区 + 近N个月
        # "查询2024年各大区销售额最高的前3个品类",          # CATEGORY_GMV by region，历史年 + 地区 + Top-N
        # "对比去年各会员等级在不同品类的客单价",           # RPC by member_level + category，多维
    ]


async def run_benchmark():
    """
    执行基准测试并输出多维度质量报告。

    统计指标说明
    ────────────────────────────────────────────────────
    成功率          output 非空，HQL 执行有结果
    空结果率        HQL 执行成功但查询结果为空
    失败率          触发熔断拒答（fallback_node）
      ├ 字段缺失降级  unfound_fields 非空导致熔断
      └ 纠错超限降级  correct_count 达上限导致熔断
    执行异常率      execute_hql_node 抛出异常
    一次通过率      correct_count == 0 且执行成功
    重试成功率      correct_count > 0 且执行成功
    平均纠错轮次    所有用例的 correct_count 均值
    ────────────────────────────────────────────────────
    """
    import time
    import dataclasses

    @dataclasses.dataclass
    class CaseResult:
        question: str
        success: bool  # output 非空
        empty_result: bool  # 执行成功但无数据
        exec_error: bool  # execute_hql_node 异常
        fallback: bool  # 触发熔断
        unfound_fallback: bool  # 字段找不到触发熔断
        correct_limit_fallback: bool  # 纠错超限触发熔断
        other_fallback: bool  # 其他原因熔断
        correct_count: int
        unfound_fields: list
        hql: str
        answer: str
        duration_ms: float
        run_error: str  # 节点/框架运行时异常

    suite = build_test_suite1()
    results: list[CaseResult] = []

    print(f"\n{'=' * 70}")
    print(f"  基准测试开始，共 {len(suite)} 条用例")
    print(f"{'=' * 70}\n")

    async with repository_factory as repositories:
        for idx, question in enumerate(suite, 1):
            task_id_context.set(uuid.uuid4().hex)
            print(f"[{idx:02d}/{len(suite)}] {question}")
            # custom chunk 收集：dict 含 output 为查询结果，str 为各类文本消息
            output: list[dict] = []
            answer: str = ""
            hql: str = ""
            correct_count: int = 0
            unfound_fields: list = []
            run_error = ""
            t0 = time.monotonic()
            try:
                async for mode, chunk in graph.astream(
                        input=InputState(question=question),
                        context=EnvContext(
                            repositories=repositories,
                            embedding_client=embedding_manager.embedding_client,
                        ),
                        stream_mode=["updates", "custom"],
                ):
                    if mode == "custom":
                        # execute_hql_node 写入 {"output": [...]}
                        if isinstance(chunk, dict) and "output" in chunk:
                            output = chunk["output"]
                        # fallback_node / execute_hql_node 写入字符串消息
                        elif isinstance(chunk, str):
                            answer = chunk
                    elif mode == "updates":
                        # 从状态更新中提取 hql / correct_count / unfound_fields
                        for node_output in chunk.values():
                            if isinstance(node_output, dict):
                                if "hql" in node_output:
                                    hql = node_output["hql"] or hql
                                if "correct_count" in node_output:
                                    correct_count = int(node_output["correct_count"] or 0)
                                if "unfound_fields" in node_output:
                                    unfound_fields = list(node_output["unfound_fields"] or [])
            except Exception as e:
                run_error = str(e)
            duration_ms = (time.monotonic() - t0) * 1000

            success = bool(output)
            exec_error = "查询执行失败" in answer
            empty_result = (not output) and (not exec_error) and (not answer or "执行完毕" in answer)
            unfound_fb = "当前数据源不包含所需字段" in answer
            correct_fb = "轮纠错后仍无法满足" in answer
            other_fb = (not success) and (not exec_error) and (not empty_result) and (not unfound_fb) and (
                not correct_fb) and bool(answer)
            fallback = unfound_fb or correct_fb or other_fb

            status = "✓ 成功" if success else (
                "○ 空结果" if empty_result else ("✗ 失败" if fallback else ("! 异常" if exec_error else "? 未知")))
            print(f"       状态={status}  纠错={correct_count}轮  耗时={duration_ms:.0f}ms")
            if run_error:
                print(f"       运行异常: {run_error}")

            results.append(CaseResult(
                question=question,
                success=success,
                empty_result=empty_result,
                exec_error=exec_error,
                fallback=fallback,
                unfound_fallback=unfound_fb,
                correct_limit_fallback=correct_fb,
                other_fallback=other_fb,
                correct_count=correct_count,
                unfound_fields=unfound_fields,
                hql=hql,
                answer=answer,
                duration_ms=duration_ms,
                run_error=run_error,
            ))

    # ── 汇总报告 ──────────────────────────────────────────────────────
    n = len(results)
    n_success = sum(r.success for r in results)
    n_empty = sum(r.empty_result for r in results)
    n_exec_error = sum(r.exec_error for r in results)
    n_fallback = sum(r.fallback for r in results)
    n_unfound_fb = sum(r.unfound_fallback for r in results)
    n_correct_fb = sum(r.correct_limit_fallback for r in results)
    n_other_fb = sum(r.other_fallback for r in results)
    n_run_error = sum(bool(r.run_error) for r in results)
    n_first_pass = sum(r.success and r.correct_count == 0 for r in results)
    n_retry_success = sum(r.success and r.correct_count > 0 for r in results)
    avg_correct = sum(r.correct_count for r in results) / n
    avg_duration = sum(r.duration_ms for r in results) / n
    max_duration = max(r.duration_ms for r in results)
    min_duration = min(r.duration_ms for r in results)

    def pct(k):
        return f"{k / n * 100:.1f}%"

    print(f"\n{'=' * 70}")
    print(f"  基准测试报告  （共 {n} 条用例）")
    print(f"{'=' * 70}")
    print(f"  {'指标':<20} {'数量':>6}  {'占比':>8}")
    print(f"  {'-' * 38}")
    print(f"  {'成功率':<20} {n_success:>6}  {pct(n_success):>8}")
    print(f"  {'  一次通过率':<20} {n_first_pass:>6}  {pct(n_first_pass):>8}")
    print(f"  {'  重试成功率':<20} {n_retry_success:>6}  {pct(n_retry_success):>8}")
    print(f"  {'空结果率':<20} {n_empty:>6}  {pct(n_empty):>8}")
    print(f"  {'失败率（熔断）':<20} {n_fallback:>6}  {pct(n_fallback):>8}")
    print(f"  {'  字段缺失降级':<20} {n_unfound_fb:>6}  {pct(n_unfound_fb):>8}")
    print(f"  {'  纠错超限降级':<20} {n_correct_fb:>6}  {pct(n_correct_fb):>8}")
    print(f"  {'  其他降级':<20} {n_other_fb:>6}  {pct(n_other_fb):>8}")
    print(f"  {'执行异常率':<20} {n_exec_error:>6}  {pct(n_exec_error):>8}")
    print(f"  {'框架运行异常':<20} {n_run_error:>6}  {pct(n_run_error):>8}")
    print(f"  {'-' * 38}")
    print(f"  {'平均纠错轮次':<20} {avg_correct:>6.2f}")
    print(f"  {'平均耗时(ms)':<20} {avg_duration:>6.0f}")
    print(f"  {'最大耗时(ms)':<20} {max_duration:>6.0f}")
    print(f"  {'最小耗时(ms)':<20} {min_duration:>6.0f}")
    print(f"{'=' * 70}")

    # ── 失败 / 异常用例明细 ──────────────────────────────────────────
    failed = [r for r in results if not r.success or r.run_error]
    if failed:
        print(f"\n  失败 / 异常用例明细（{len(failed)} 条）：")
        for r in failed:
            tag = []
            if r.unfound_fallback:      tag.append(f"字段缺失{r.unfound_fields}")
            if r.correct_limit_fallback: tag.append(f"纠错超限({r.correct_count}轮)")
            if r.exec_error:            tag.append("执行异常")
            if r.other_fallback:        tag.append("其他熔断")
            if r.run_error:             tag.append(f"框架异常:{r.run_error}")
            print(f"  ✗ {r.question}")
            print(f"    原因: {' | '.join(tag)}")
            if r.hql:
                hql_preview = r.hql.replace('\n', ' ')[:120]
                print(f"    HQL : {hql_preview}{'...' if len(r.hql) > 120 else ''}")
    print(f"{'=' * 70}\n")


if __name__ == '__main__':
    print(graph.get_graph().draw_mermaid())

    # asyncio.run(run_benchmark())
