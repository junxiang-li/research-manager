# -*- coding: utf-8 -*-
"""结题素材汇编导出：Word / Markdown。不生成完整结题报告，只导出可复制进官方模板的素材。"""
import io
import os
from datetime import date

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

from db import db
from logic import build_indicator_table, project_progress


def _set_cn_font(run, name="宋体", size=10.5, bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)


def _fill_cell(cell, text, bold=False, size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    r = p.add_run(str(text if text is not None else ""))
    _set_cn_font(r, "宋体", size, bold)


def gather(project_id):
    with db() as conn:
        proj = dict(conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone() or {})
        inds = build_indicator_table(conn, project_id)
        contents = [dict(r) for r in conn.execute(
            "SELECT * FROM research_contents WHERE project_id=? ORDER BY order_num,id", (project_id,))]
        achs = [dict(r) for r in conn.execute("""
            SELECT DISTINCT a.* FROM achievements a
            LEFT JOIN achievement_projects ap ON ap.achievement_id=a.id
            LEFT JOIN achievement_indicators ai ON ai.achievement_id=a.id
            LEFT JOIN indicators i ON i.id=ai.indicator_id
            WHERE ap.project_id=? OR i.project_id=?
            ORDER BY a.ach_type, a.id
        """, (project_id, project_id))]
        budget = [dict(r) for r in conn.execute(
            "SELECT * FROM budget_items WHERE project_id=? ORDER BY id", (project_id,))]
        expenses = [dict(r) for r in conn.execute(
            "SELECT * FROM expenses WHERE project_id=? ORDER BY expense_date,id", (project_id,))]
        progress = project_progress(conn, project_id)
    return {
        "project": proj, "indicators": inds, "contents": contents,
        "achievements": achs, "budget": budget, "expenses": expenses,
        "progress": progress, "generated": date.today().isoformat(),
    }


def export_markdown(project_id):
    d = gather(project_id)
    p = d["project"]
    lines = [f"# {p.get('name','项目')} — 结题素材汇编", "",
             f"> 生成日期：{d['generated']}　|　整体完成度：{d['progress']['progress']}%（{d['progress']['mode']} 模式）", ""]

    lines += ["## 一、项目基本信息汇总", "", "| 字段 | 内容 |", "| --- | --- |"]
    for label, key in [("项目名称", "name"), ("立项编号", "code"), ("项目来源", "source"),
                       ("负责人", "leader"), ("起止时间", "start_date"), ("经费总额（万元）", "budget"),
                       ("合作单位", "partners"), ("项目状态", "status")]:
        val = p.get(key, "")
        if key == "start_date" and p.get("end_date"):
            val = f"{p.get('start_date','')} 至 {p['end_date']}"
        lines.append(f"| {label} | {val} |")
    lines.append("")

    lines += ["## 二、考核指标完成情况对照表", "",
              "| 研究内容 | 考核指标 | 类型 | 目标值 | 已完成 | 缺口 | 完成度 | 状态 | 支撑成果 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i in d["indicators"]:
        ach = "、".join(a["title"] for a in i["achievements"]) or "—"
        status = {"ok": "正常/完成", "warn": "预警", "danger": "超期/缺口"}[i["warning"]]
        lines.append(f"| {i.get('content_title') or '—'} | {i['title']} | {'定量' if i['ind_type']=='quantitative' else '定性'} | "
                     f"{i['target_value']}{i.get('unit') or ''} | {i['completed']} | {i['gap']} | {i['progress']}% | {status} | {ach} |")
    lines.append("")

    lines += ["## 三、成果清单", "", "| 序号 | 成果名称 | 类型 | 等级 | 状态 | 标注资助号 | 编号/DOI | 附件 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for n, a in enumerate(d["achievements"], 1):
        lines.append(f"| {n} | {a['title']} | {a['ach_type']} | {a.get('level') or '—'} | {a.get('status') or '—'} | "
                     f"{'是' if a.get('funding_ack') else '否'} | {a.get('identifier') or '—'} | {a.get('file_path') or '—'} |")
    lines.append("")

    lines += ["## 四、研究内容进展简述（素材）", ""]
    for c in d["contents"]:
        lines += [f"### {c['title']}", "", c.get("description") or "（待补充进展描述）", ""]
        rel = [i for i in d["indicators"] if i.get("content_id") == c["id"]]
        if rel:
            lines.append("关联指标：" + "；".join(
                f"{i['title']}（{i['completed']}/{i['target_value']}{i.get('unit') or ''}，{i['progress']}%）" for i in rel))
            lines.append("")

    lines += ["## 五、经费执行汇总", "", "| 预算科目 | 预算（万元） | 支出（万元） | 执行率 |",
              "| --- | --- | --- | --- |"]
    for b in d["budget"]:
        spend = sum(e["amount"] or 0 for e in d["expenses"] if e.get("budget_item_id") == b["id"])
        rate = round(spend / b["budget"] * 100, 1) if b["budget"] else 0
        lines.append(f"| {b['category']} | {b['budget']} | {round(spend,2)} | {rate}% |")
    lines.append("")
    return "\n".join(lines)


def export_docx(project_id):
    d = gather(project_id)
    p = d["project"]
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = Cm(2.5); sec.right_margin = Cm(2.5)

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_cn_font(h.add_run(f"{p.get('name','项目')} — 结题素材汇编"), "黑体", 16, True)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_cn_font(sub.add_run(f"生成日期：{d['generated']}　|　整体完成度：{d['progress']['progress']}%"), "仿宋", 10.5)
    doc.add_paragraph()

    def heading(text):
        para = doc.add_paragraph()
        _set_cn_font(para.add_run(text), "黑体", 13, True)

    # 一、基本信息
    heading("一、项目基本信息汇总")
    t = doc.add_table(rows=0, cols=2); t.style = "Table Grid"
    fields = [("项目名称", "name"), ("立项编号", "code"), ("项目来源", "source"),
              ("负责人", "leader"), ("起止时间", "start_date"), ("经费总额（万元）", "budget"),
              ("合作单位", "partners"), ("项目状态", "status")]
    for label, key in fields:
        row = t.add_row().cells
        val = p.get(key, "")
        if key == "start_date" and p.get("end_date"):
            val = f"{p.get('start_date','')} 至 {p['end_date']}"
        _fill_cell(row[0], label, bold=True); _fill_cell(row[1], val)

    # 二、指标对照表（核心表）
    doc.add_paragraph()
    heading("二、考核指标完成情况对照表")
    t2 = doc.add_table(rows=1, cols=9); t2.style = "Table Grid"
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["研究内容", "考核指标", "类型", "目标值", "已完成", "缺口", "完成度", "状态", "支撑成果"]
    for j, htext in enumerate(headers):
        _fill_cell(t2.rows[0].cells[j], htext, bold=True, size=8)
    for i in d["indicators"]:
        cells = t2.add_row().cells
        ach = "、".join(a["title"] for a in i["achievements"]) or "—"
        status = {"ok": "正常/完成", "warn": "预警", "danger": "超期/缺口"}[i["warning"]]
        vals = [i.get("content_title") or "—", i["title"], "定量" if i["ind_type"] == "quantitative" else "定性",
                f"{i['target_value']}{i.get('unit') or ''}", i["completed"], i["gap"], f"{i['progress']}%", status, ach]
        for j, v in enumerate(vals):
            _fill_cell(cells[j], v, size=8)

    # 三、成果清单
    doc.add_paragraph()
    heading("三、成果清单")
    t3 = doc.add_table(rows=1, cols=8); t3.style = "Table Grid"
    for j, htext in enumerate(["序号", "成果名称", "类型", "等级", "状态", "标注资助号", "编号/DOI", "附件路径"]):
        _fill_cell(t3.rows[0].cells[j], htext, bold=True, size=8)
    for n, a in enumerate(d["achievements"], 1):
        cells = t3.add_row().cells
        vals = [n, a["title"], a["ach_type"], a.get("level") or "—", a.get("status") or "—",
                "是" if a.get("funding_ack") else "否", a.get("identifier") or "—", a.get("file_path") or "—"]
        for j, v in enumerate(vals):
            _fill_cell(cells[j], v, size=8)

    # 四、研究内容进展
    doc.add_paragraph()
    heading("四、研究内容进展简述（素材）")
    for c in d["contents"]:
        para = doc.add_paragraph()
        _set_cn_font(para.add_run(c["title"]), "黑体", 11, True)
        body = doc.add_paragraph()
        _set_cn_font(body.add_run(c.get("description") or "（待补充进展描述）"), "仿宋", 10.5)
        rel = [i for i in d["indicators"] if i.get("content_id") == c["id"]]
        if rel:
            txt = "关联指标：" + "；".join(
                f"{i['title']}（{i['completed']}/{i['target_value']}{i.get('unit') or ''}，{i['progress']}%）" for i in rel)
            bp = doc.add_paragraph()
            _set_cn_font(bp.add_run(txt), "仿宋", 10.5)

    # 五、经费执行
    doc.add_paragraph()
    heading("五、经费执行汇总")
    t4 = doc.add_table(rows=1, cols=4); t4.style = "Table Grid"
    for j, htext in enumerate(["预算科目", "预算（万元）", "支出（万元）", "执行率"]):
        _fill_cell(t4.rows[0].cells[j], htext, bold=True)
    for b in d["budget"]:
        spend = sum(e["amount"] or 0 for e in d["expenses"] if e.get("budget_item_id") == b["id"])
        rate = round(spend / b["budget"] * 100, 1) if b["budget"] else 0
        cells = t4.add_row().cells
        for j, v in enumerate([b["category"], b["budget"], round(spend, 2), f"{rate}%"]):
            _fill_cell(cells[j], v)

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
