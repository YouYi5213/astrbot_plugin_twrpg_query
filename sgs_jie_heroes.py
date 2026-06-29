"""三国杀「界」武将名单 — 用于拦截误用「界」物品查询前缀的玩家。"""

from __future__ import annotations

from .data_loader import normalize_query

# 界标 + 界风林火山 + 常见界将（来源：三国杀界限突破标准版及风林火山扩展）
SGS_JIE_HERO_NAMES: tuple[str, ...] = (
    # 界·标 魏
    "曹操",
    "司马懿",
    "夏侯惇",
    "张辽",
    "许褚",
    "郭嘉",
    "甄姬",
    "李典",
    # 界·标 蜀
    "刘备",
    "关羽",
    "张飞",
    "诸葛亮",
    "赵云",
    "马超",
    "黄月英",
    "徐庶",
    # 界·标 吴
    "孙权",
    "甘宁",
    "吕蒙",
    "黄盖",
    "周瑜",
    "大乔",
    "陆逊",
    "孙尚香",
    # 界·标 群
    "华佗",
    "吕布",
    "貂蝉",
    "华雄",
    "袁术",
    "公孙瓒",
    # 界·风
    "夏侯渊",
    "曹仁",
    "黄忠",
    "魏延",
    "小乔",
    "周泰",
    "张角",
    "于吉",
    # 界·火
    "典韦",
    "荀彧",
    "庞统",
    "太史慈",
    "袁绍",
    "庞德",
    "颜良文丑",
    "卧龙诸葛亮",
    "卧龙",
    # 界·林
    "曹丕",
    "徐晃",
    "孟获",
    "祝融",
    "孙坚",
    "鲁肃",
    "董卓",
    "贾诩",
    # 界·山
    "张郃",
    "邓艾",
    "姜维",
    "刘禅",
    "孙策",
    "张昭张纮",
    "左慈",
    "蔡文姬",
    # 常见别名
    "颜良&文丑",
    "张昭&张纮",
    # 后续常见界将（移动版/OL）
    "法正",
    "高顺",
    "陈宫",
    "曹植",
    "于禁",
    "张春华",
    "马谡",
    "吴国太",
    "凌统",
    "步练师",
    "满宠",
    "郭淮",
    "曹冲",
    "钟会",
    "蔡夫人",
)

SGS_JIE_HERO_KEYS: frozenset[str] = frozenset(
    normalize_query(name) for name in SGS_JIE_HERO_NAMES if name
)

SGS_JIE_REPLY = "滚回去玩你的三国杀！"


def is_sgs_jie_hero_query(query: str) -> bool:
    key = normalize_query(query)
    if not key:
        return False
    return key in SGS_JIE_HERO_KEYS
