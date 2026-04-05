def clean_code_block(text: str) -> str:
    """去掉文本里的代码块包裹"""
    import re
    text = text.strip()
    # 去掉开头的 ```xxx（带或不带语言标识符）
    text = re.sub(r'^```[a-z]*\n?', '', text, count=1)
    # 去掉结尾的 ```
    if text.endswith("```"):
        text = text.removesuffix("```").strip()
    return text.strip()


def extract_hql(text: str) -> str:
    """
    从混合文本（分析说明 + HQL）中截取最后一段合法的 HQL 语句。

    策略：找到最后一行以 SELECT 或 WITH 开头（行首无缩进）的行，
    将该行及其后的全部内容作为 HQL 返回，丢弃前面的分析文本。
    若找不到符合条件的行，原样返回（避免丢失内容）。

    行首无缩进的限制用于排除子查询中的 SELECT，只匹配顶层语句起始行。
    """
    import re
    text = text.strip()
    lines = text.splitlines()
    sql_start = -1
    for i, line in enumerate(lines):
        if re.match(r'^(SELECT|WITH)\b', line, re.IGNORECASE):
            sql_start = i
    if sql_start >= 0:
        return '\n'.join(lines[sql_start:]).strip()
    return text
