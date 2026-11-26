# -*- coding: utf-8 -*-
"""进度与预警计算逻辑（后端与导出共用）。"""
from datetime import date, datetime


def _parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(str(s)[:10] if fmt == "%Y-%m-%d" else str(s), fmt).date()
        except Exception:
            pass
    return None


def indicator_stats(conn, ind_id):
    """返回单条指标的完成数、进度、支撑成果列表。"""
    rows = conn.execute("""
        SELECT a.id, a.title, a.ach_type, a.status, a.level, a.identifier, a.file_path
        FROM achievement_indicators ai
        JOIN achievements a ON a.id = ai.achievement_id
        WHERE ai.indicator_id = ?
        ORDER BY a.id
    """, (ind_id,)).fetchall()
    ind = conn.execute("SELECT * FROM indicators WHERE id = ?", (ind_id,)).fetchone()
    if not ind:
        return {"completed": 0, "progress": 0, "achievements": []}
    completed = len(rows)
    if ind["manual_done"]:
        completed = max(completed, 1)
    target = ind["target_value"] or 1
    progress = min(round(completed / target * 100, 1), 100) if ind["ind_type"] == "quantitative" else (100 if completed or ind["manual_done"] else 0)
    return {"completed": completed, "progress": progress, "achievements": [dict(r) for r in rows]}


def project_progress(conn, project_id):
    """项目整体完成度：按权重模式对所有定量/定性指标加权平均；权重缺失时退回计数平均。"""
    inds = conn.execute("SELECT * FROM indicators WHERE project_id = ?", (project_id,)).fetchall()
    if not inds:
        return {"progress": 0, "mode": "weight", "count": 0}
    vals = []
    for ind in inds:
        st = indicator_stats(conn, ind["id"])
        w = ind["weight"] if ind["weight"] and ind["weight"] > 0 else 0
        vals.append((st["progress"], w))
    total_w = sum(w for _, w in vals)
    if total_w > 0:
        return {"progress": round(sum(p * w for p, w in vals) / total_w, 1), "mode": "weight", "count": len(inds)}
    return {"progress": round(sum(p for p, _ in vals) / len(vals), 1), "mode": "count", "count": len(inds)}


def warning_level(ind, progress, today=None):
    """预警：danger 红 / warn 黄 / ok 绿。两维度取较重者，结果可解释。

    维度1-时间：已过截止 → 红；30 天内到期 → 黄。
    维度2-缺口：以项目整体周期进度为参照（不用单指标 deadline 做分母，避免临近截止时虚高），
               落后 ≥40% → 红；≥20% → 黄。
    """
    today = today or date.today()
    deadline = _parse_date(ind["deadline"])
    if progress >= 100 or ind["manual_done"]:
        return "ok", "已完成"

    level, reason = "ok", "正常"

    # 维度1：截止时间
    if deadline:
        days_left = (deadline - today).days
        if days_left < 0:
            level, reason = "danger", f"超期 {-days_left} 天"
        elif days_left <= 30:
            level, reason = "warn", f"{days_left} 天后到期"

    # 维度2：相对项目周期的缺口
    start = _parse_date(ind.get("_proj_start"))
    end = _parse_date(ind.get("_proj_end"))
    if start and end and end > start:
        time_progress = (today - start).days / (end - start).days * 100
        gap = time_progress - progress
        if gap >= 40 and level != "danger":
            level, reason = "danger", f"进度落后 {gap:.0f}%"
        elif gap >= 20 and level == "ok":
            level, reason = "warn", f"进度落后 {gap:.0f}%"
    return level, reason


def build_indicator_table(conn, project_id):
    """结题对照表数据源：所有指标 + 统计 + 预警 + 项目时间边界。"""
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    pdict = dict(proj) if proj else {}
    inds = conn.execute("""
        SELECT i.*, rc.title AS content_title
        FROM indicators i LEFT JOIN research_contents rc ON rc.id = i.content_id
        WHERE i.project_id = ? ORDER BY rc.order_num, i.order_num, i.id
    """, (project_id,)).fetchall()
    out = []
    for ind in inds:
        d = dict(ind)
        d["_proj_start"] = pdict.get("start_date")
        d["_proj_end"] = pdict.get("end_date")
        st = indicator_stats(conn, d["id"])
        d.update(st)
        level, reason = warning_level(d, st["progress"])
        d["warning"], d["warning_reason"] = level, reason
        d["gap"] = max(0, (d["target_value"] or 0) - st["completed"]) if d["ind_type"] == "quantitative" else (0 if st["progress"] >= 100 else 1)
        out.append(d)
    return out
