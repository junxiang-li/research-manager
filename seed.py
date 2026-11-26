# -*- coding: utf-8 -*-
"""种子数据：一套占位演示数据（不对应任何真实项目、单位、人员或成果），可直接运行体验，也可清空后录入自己的数据。"""
from db import db, init_db
from datetime import date

init_db()

with db() as conn:
    # 幂等：已有项目则跳过
    if conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] > 0:
        print("已有数据，跳过种子写入。如需重置请删除 data/research.db")
        raise SystemExit

    cur = conn.execute("""INSERT INTO projects(name,code,source,leader,start_date,end_date,budget,partners,note,status)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("示例科研项目一（占位）", "XXXXXXX", "国自科", "示例负责人", "2023-01-01", "2026-12-31", 62.0,
         "示例合作单位（占位）", "演示用：面向复杂环境的可学习规划方法研究", "在研"))
    pid = cur.lastrowid

    cur2 = conn.execute("""INSERT INTO projects(name,code,source,leader,start_date,end_date,budget,partners,note,status)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        ("示例科研项目二（占位）", "XXXXXXX", "省重点研发", "示例负责人", "2025-06-01", "2027-05-31", 120.0,
         "示例合作单位（占位）", "演示用：多平台共性组件与接口标准化", "在研"))
    pid2 = cur2.lastrowid

    # 基准快照 + 变更版本
    conn.execute("""INSERT INTO project_docs(project_id,doc_type,title,version_tag,is_baseline,change_date,summary)
        VALUES(?,?,?,?,?,?,?)""", (pid, "任务书", "任务书（示例）", "V1.0", 1, "2023-01-01", "原始任务基准：论文5篇、专利2项、样机1套，2026-12结题"))
    conn.execute("""INSERT INTO project_docs(project_id,doc_type,title,version_tag,is_baseline,change_date,summary)
        VALUES(?,?,?,?,?,?,?)""", (pid, "任务调整单", "指标调整批复（示例）", "V2.0", 0, "2025-06-15",
        "论文由5篇调整为4篇；新增试验报告2份；结题延期至2026-12-31（原2026-06-30）"))

    # 研究内容
    cids = {}
    for k, (title, desc) in enumerate([
        ("研究内容1　复杂环境可通行性建模", "基于视觉与激光融合的地形语义分割与可通行性评估"),
        ("研究内容2　可学习模块化规划方法", "将感知、决策、规划模块化并实现端到端可学习策略"),
        ("研究内容3　平台集成与实地验证", "构建移动平台样机并在典型场景开展试验验证"),
    ], 1):
        cur = conn.execute("INSERT INTO research_contents(project_id,title,description,order_num) VALUES(?,?,?,?)",
                           (pid, title, desc, k))
        cids[k] = cur.lastrowid

    # 考核指标（定量 + 定性）
    inds = [
        (cids[1], "发表期刊论文", "quantitative", 4, "篇", "2026-09-30", 30, 0),
        (cids[1], "申请发明专利", "quantitative", 2, "项", "2026-06-30", 20, 0),
        (cids[2], "开发软件著作权", "quantitative", 2, "项", "2026-09-30", 10, 0),
        (cids[3], "研制移动平台样机", "quantitative", 1, "套", "2026-10-31", 25, 0),
        (cids[3], "提交试验报告", "quantitative", 2, "份", "2026-11-30", 15, 0),
        (cids[2], "完成方案论证与仿真平台搭建", "qualitative", 1, "", "2024-12-31", 0, 1),
    ]
    iids = []
    for content_id, title, itype, target, unit, deadline, weight, done in inds:
        cur = conn.execute("""INSERT INTO indicators(project_id,content_id,title,ind_type,target_value,unit,deadline,weight,manual_done,order_num)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (pid, content_id, title, itype, target, unit, deadline, weight, done, len(iids)))
        iids.append(cur.lastrowid)

    # 成果库（全局，含多项目复用）
    ach_defs = [
        ("示例论文一：双分支语义分割方法（占位）", "期刊论文", "录用", "TOP期刊", "作者 等", "示例期刊", "2025-08", "DOI: 占位", 1, "XXXXXXX", [(pid, iids[0]), (pid2, None)]),
        ("示例专利一：环境可通行性判定方法（占位）", "发明专利", "授权", "普通", "作者 等", "", "2025-03", "专利号：占位", 1, "XXXXXXX", [(pid, iids[1])]),
        ("示例软件一：模块化规划软件 V1.0（占位）", "软件著作权", "已交付", "普通", "作者 等", "", "2025-11", "软著号：占位", 1, "XXXXXXX", [(pid, iids[2]), (pid2, None)]),
        ("示例试验报告一：复杂地形规划系统（占位）", "试验报告", "已交付", "普通", "课题组", "", "2026-01", "", 1, "XXXXXXX", [(pid, iids[4])]),
        ("示例会议论文一：基于强化学习的重规划（占位）", "会议论文", "在投", "普通", "作者 等", "示例会议", "2026-03", "", 0, "", [(pid, iids[0])]),
        ("示例样机一：移动平台（占位）", "样机", "已交付", "普通", "课题组", "", "2025-12", "", 0, "", [(pid, iids[3])]),
    ]
    aids = []
    for title, atype, status, level, authors, journal, pubdate, ident, funded, fcode, links in ach_defs:
        cur = conn.execute("""INSERT INTO achievements(title,ach_type,status,level,authors,journal,pub_date,identifier,funding_ack,funding_code,is_public,source,note)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, atype, status, level, authors, journal, pubdate, ident, funded, fcode, 1, "seed", ""))
        aid = cur.lastrowid
        aids.append(aid)
        for proj_id, ind_id in links:
            conn.execute("INSERT OR IGNORE INTO achievement_projects(achievement_id,project_id) VALUES(?,?)", (aid, proj_id))
            if ind_id:
                conn.execute("INSERT INTO achievement_indicators(achievement_id,indicator_id) VALUES(?,?)", (aid, ind_id))

    # 经费
    for cat, amt in [("设备费", 25), ("材料费", 8), ("测试化验加工费", 10), ("差旅费", 6), ("劳务费", 9), ("专家咨询费", 3), ("间接费用", 1)]:
        conn.execute("INSERT INTO budget_items(project_id,category,budget) VALUES(?,?,?)", (pid, cat, amt))
    for bid_row in conn.execute("SELECT id,category,budget FROM budget_items WHERE project_id=?", (pid,)):
        ratio = {"设备费": .9, "材料费": .7, "测试化验加工费": .5, "差旅费": .8, "劳务费": .6}.get(bid_row["category"], .3)
        conn.execute("INSERT INTO expenses(project_id,budget_item_id,amount,expense_date,description,voucher) VALUES(?,?,?,?,?,?)",
                     (pid, bid_row["id"], round(bid_row["budget"] * ratio, 2), "2025-12-20", "年度经费支出", "FP2025-XXX"))

print("种子数据写入完成:", pid, pid2)
