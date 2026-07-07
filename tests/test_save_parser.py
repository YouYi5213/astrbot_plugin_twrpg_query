from core.save_parser import parse_string_for_stage


SAMPLE = """
call Preload("游戏ID:10001
职业:战士
等级:80
游戏版本:1.0
兼容版本:1.0
----------账号物品----------
1. 不朽者徽章
----------携带物品----------
普瑞斯银币 x10
----------背包----------
测试材料A
----------仓库----------
材料B
")
"""


def test_parse_string_for_stage():
    data = parse_string_for_stage(SAMPLE)
    assert data.game_id == "10001"
    assert data.job == "战士"
    assert data.level == "80"
    assert data.account_badge_display == "不朽者徽章"
    assert len(data.carried_items) == 1
    assert len(data.backpack_items) == 1
    assert len(data.warehouse_items) == 1


def test_flexible_section_headers():
    content = """
call Preload("---------- 携带物品 ----------
测试币 x1
---------- 背包 ----------
1. 材料A
---------- 仓库 ----------
材料B
材料C
")
"""
    data = parse_string_for_stage(content)
    assert len(data.carried_items) == 1
    assert len(data.backpack_items) == 1
    assert len(data.warehouse_items) == 2
