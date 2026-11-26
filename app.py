# -*- coding: utf-8 -*-
"""科研项目管理软件 — Flask 后端 API。"""
import os
import io
import sys
import json
import time
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, Response, send_file

from db import init_db, db, DB_PATH, FILES_ROOT
from logic import build_indicator_table, project_progress, indicator_stats
from parser import scan_folder, parse_pdf, archive_file, to_rel_path
from exporter import export_docx, export_markdown

# 打包为 exe 后静态资源在临时解压目录 sys._MEIPASS 下；源码运行则在脚本同目录
if getattr(sys, "frozen", False):
    STATIC_DIR = os.path.join(sys._MEIPASS, "static")
else:
    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
init_db()


# ---------- 工具 ----------
def body():
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        d = request.form.to_dict()
        for k in ("funding_ack", "is_public", "is_baseline", "manual_done"):
            if k in d:
                d[k] = 1 if str(d[k]).lower() in ("1", "true", "on", "yes") else 0
        return d
    return {}


def ok(data=None, **kw):
    d = {"ok": True}
    if data is not None:
        d["data"] = data
    d.update(kw)
    return jsonify(d)


def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def save_upload(file_storage, subdir="docs"):
    if not file_storage or not file_storage.filename:
        return "", ""
    safe = os.path.basename(file_storage.filename.replace("\\", "/"))
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    name = f"{stamp}_{safe}"
    dest_dir = os.path.join(FILES_ROOT, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, name)
    file_storage.save(path)
    return f"{subdir}/{name}", safe


def sync_budget_from_meta(conn, pid, new_total, old_total=None):
    """把项目元信息经费总额按比例同步到该项目的预算科目，使科目合计 == 元信息总额。
    保留科目结构与相对比例；无科目时生成一条「预算总额」科目。返回同步结果。"""
    new_total = round(float(new_total or 0), 2)
    items = conn.execute("SELECT id,budget FROM budget_items WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    if not items:
        if new_total > 0:
            conn.execute("INSERT INTO budget_items(project_id,category,budget,note) VALUES(?,?,?,?)",
                         (pid, "预算总额", new_total, "由项目元信息经费总额同步生成"))
            return {"synced": 1, "total": new_total}
        return {"synced": 0, "total": 0}
    old_sum = sum((i["budget"] or 0) for i in items)
    if old_sum > 0:
        alloc = [round(new_total * (i["budget"] or 0) / old_sum, 2) for i in items]
    else:
        per = round(new_total / len(items), 2)
        alloc = [per] * len(items)
    # 末条补齐四舍五入误差，保证合计精确等于元信息总额
    alloc[-1] = round(alloc[-1] + round(new_total - sum(alloc), 2), 2)
    for it, amt in zip(items, alloc):
        conn.execute("UPDATE budget_items SET budget=? WHERE id=?", (amt, it["id"]))
    return {"synced": len(items), "total": round(sum(alloc), 2)}


# ---------- 前端 ----------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------- 仪表盘 ----------
@app.route("/api/dashboard")
def api_dashboard():
    with db() as conn:
        projects = [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]
        for p in projects:
            p["progress"] = project_progress(conn, p["id"])["progress"]
            p["ach_count"] = conn.execute("""SELECT COUNT(DISTINCT a.id) FROM achievements a
                LEFT JOIN achievement_projects ap ON ap.achievement_id=a.id
                LEFT JOIN achievement_indicators ai ON ai.achievement_id=a.id
                LEFT JOIN indicators i ON i.id=ai.indicator_id
                WHERE ap.project_id=? OR i.project_id=?""", (p["id"], p["id"])).fetchone()[0]
        total_ach = conn.execute("SELECT COUNT(*) FROM achievements").fetchone()[0]
        no_funding = conn.execute("SELECT COUNT(*) FROM achievements WHERE funding_ack=0").fetchone()[0]
        warns = []
        for p in projects:
            for i in build_indicator_table(conn, p["id"]):
                if i["warning"] != "ok":
                    warns.append({"project": p["name"], "project_id": p["id"],
                                  "indicator": i["title"], "warning": i["warning"],
                                  "reason": i["warning_reason"], "progress": i["progress"]})
        warns.sort(key=lambda x: (0 if x["warning"] == "danger" else 1))
    return ok({"projects": projects, "total_achievements": total_ach,
               "no_funding_count": no_funding, "warnings": warns})


# ---------- 项目库 ----------
@app.route("/api/projects", methods=["GET", "POST"])
def api_projects():
    if request.method == "GET":
        with db() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id")]
            for r in rows:
                r["progress"] = project_progress(conn, r["id"])["progress"]
        return ok(rows)
    d = body()
    if not d.get("name"):
        return fail("项目名称必填")
    with db() as conn:
        cur = conn.execute("""INSERT INTO projects(name,code,source,leader,start_date,end_date,budget,partners,note,status)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (d.get("name"), d.get("code", ""), d.get("source", ""), d.get("leader", ""),
             d.get("start_date", ""), d.get("end_date", ""), float(d.get("budget") or 0),
             d.get("partners", ""), d.get("note", ""), d.get("status", "在研")))
        pid = cur.lastrowid
    return ok({"id": pid}, message="项目已创建")


@app.route("/api/projects/<int:pid>", methods=["GET", "PUT", "DELETE"])
def api_project(pid):
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            return fail("项目不存在", 404)
        if request.method == "GET":
            data = dict(row)
            data["progress"] = project_progress(conn, pid)
            return ok(data)
        if request.method == "DELETE":
            conn.execute("DELETE FROM projects WHERE id=?", (pid,))
            return ok(message="项目已删除")
        d = body()
        fields = ["name", "code", "source", "leader", "start_date", "end_date", "budget",
                  "partners", "note", "status"]
        sets, vals = [], []
        new_budget = None
        for f in fields:
            if f in d:
                sets.append(f"{f}=?")
                v = float(d[f]) if f == "budget" else d[f]
                if f == "budget":
                    new_budget = v
                vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')")
            conn.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", vals + [pid])
        # 需求1：元信息经费总额变更时，按比例同步财务预算科目，保持两处一致
        sync_info = None
        if new_budget is not None and abs(new_budget - (row["budget"] or 0)) > 1e-6:
            sync_info = sync_budget_from_meta(conn, pid, new_budget, row["budget"])
        return ok({"budget_synced": sync_info},
                  message="已保存" + ("，财务预算已同步" if sync_info else ""))


# ---------- 项目文档 / 基准快照 ----------
@app.route("/api/projects/<int:pid>/docs", methods=["GET", "POST"])
def api_docs(pid):
    with db() as conn:
        if request.method == "GET":
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM project_docs WHERE project_id=? ORDER BY is_baseline DESC, change_date DESC, id DESC", (pid,))]
            return ok(rows)
        d = body()
        if not d.get("doc_type"):
            return fail("文档类型必填")
        rel, original = save_upload(request.files.get("file"))
        conn.execute("""INSERT INTO project_docs(project_id,doc_type,title,file_path,file_name,is_baseline,version_tag,change_date,summary)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (pid, d.get("doc_type"), d.get("title", ""), rel, original,
             int(d.get("is_baseline", 0)), d.get("version_tag", ""), d.get("change_date", ""), d.get("summary", "")))
        return ok(message="文档已上传")


@app.route("/api/docs/<int:did>", methods=["DELETE"])
def api_doc_delete(did):
    with db() as conn:
        conn.execute("DELETE FROM project_docs WHERE id=?", (did,))
    return ok(message="已删除")


@app.route("/api/files/<path:rel>")
def api_file(rel):
    return send_from_directory(FILES_ROOT, rel, as_attachment=False)


# ---------- 研究内容 ----------
@app.route("/api/projects/<int:pid>/contents", methods=["GET", "POST"])
def api_contents(pid):
    with db() as conn:
        if request.method == "GET":
            return ok([dict(r) for r in conn.execute(
                "SELECT * FROM research_contents WHERE project_id=? ORDER BY order_num,id", (pid,))])
        d = body()
        if not d.get("title"):
            return fail("研究内容标题必填")
        cur = conn.execute("INSERT INTO research_contents(project_id,title,description,order_num) VALUES(?,?,?,?)",
                           (pid, d["title"], d.get("description", ""), int(d.get("order_num", 0))))
        return ok({"id": cur.lastrowid}, message="已添加")


@app.route("/api/contents/<int:cid>", methods=["PUT", "DELETE"])
def api_content(cid):
    with db() as conn:
        if request.method == "DELETE":
            conn.execute("DELETE FROM research_contents WHERE id=?", (cid,))
            return ok(message="已删除")
        d = body()
        sets, vals = [], []
        for f in ("title", "description", "order_num"):
            if f in d:
                sets.append(f"{f}=?"); vals.append(d[f])
        if sets:
            conn.execute(f"UPDATE research_contents SET {','.join(sets)} WHERE id=?", vals + [cid])
        return ok(message="已保存")


# ---------- 考核指标 ----------
@app.route("/api/projects/<int:pid>/indicators", methods=["GET", "POST"])
def api_indicators(pid):
    with db() as conn:
        if request.method == "GET":
            return ok(build_indicator_table(conn, pid))
        d = body()
        if not d.get("title"):
            return fail("指标名称必填")
        cur = conn.execute("""INSERT INTO indicators(project_id,content_id,title,ind_type,target_value,unit,deadline,weight,progress_mode,description,manual_done,order_num)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, d.get("content_id") or None, d["title"], d.get("ind_type", "quantitative"),
             float(d.get("target_value") or 1), d.get("unit", ""), d.get("deadline", ""),
             float(d.get("weight") or 0), d.get("progress_mode", "count"), d.get("description", ""),
             int(d.get("manual_done", 0)), int(d.get("order_num", 0))))
        return ok({"id": cur.lastrowid}, message="指标已添加")


@app.route("/api/indicators/<int:iid>", methods=["PUT", "DELETE"])
def api_indicator(iid):
    with db() as conn:
        if request.method == "DELETE":
            conn.execute("DELETE FROM indicators WHERE id=?", (iid,))
            return ok(message="已删除")
        d = body()
        fields = ("content_id", "title", "ind_type", "target_value", "unit", "deadline",
                  "weight", "progress_mode", "description", "manual_done", "order_num")
        sets, vals = [], []
        for f in fields:
            if f in d:
                v = d[f]
                if f in ("target_value", "weight"):
                    v = float(v or 0)
                if f in ("content_id", "manual_done", "order_num"):
                    v = int(v or 0) or None if f == "content_id" else int(v or 0)
                sets.append(f"{f}=?"); vals.append(v)
        if sets:
            conn.execute(f"UPDATE indicators SET {','.join(sets)} WHERE id=?", vals + [iid])
        return ok(message="已保存")


# ---------- 指标支撑成果反查 ----------
@app.route("/api/indicators/<int:iid>/achievements")
def api_indicator_achievements(iid):
    with db() as conn:
        st = indicator_stats(conn, iid)
    return ok(st)


# ---------- 成果库（全局） ----------
ACH_FIELDS = ("title", "ach_type", "status", "level", "authors", "journal", "pub_date",
              "identifier", "funding_ack", "funding_code", "is_public", "file_path",
              "file_name", "source", "note")


@app.route("/api/achievements", methods=["GET", "POST"])
def api_achievements():
    if request.method == "GET":
        project_id = request.args.get("project_id")
        kw = request.args.get("kw", "").strip()
        where, params = [], []
        if project_id:
            where.append("""(a.id IN (SELECT achievement_id FROM achievement_projects WHERE project_id=?)
                         OR a.id IN (SELECT ai.achievement_id FROM achievement_indicators ai
                                     JOIN indicators i ON i.id=ai.indicator_id WHERE i.project_id=?))""")
            params += [project_id, project_id]
        if kw:
            where.append("(a.title LIKE ? OR a.authors LIKE ? OR a.identifier LIKE ?)")
            params += [f"%{kw}%"] * 3
        sql = "SELECT DISTINCT a.* FROM achievements a"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY a.ach_type, a.id DESC"
        with db() as conn:
            rows = [dict(r) for r in conn.execute(sql, params)]
            for r in rows:
                r["indicators"] = [dict(x) for x in conn.execute("""
                    SELECT ai.indicator_id, ai.content_id, i.title AS indicator_title, i.project_id
                    FROM achievement_indicators ai JOIN indicators i ON i.id=ai.indicator_id
                    WHERE ai.achievement_id=?""", (r["id"],))]
                r["projects"] = [dict(x) for x in conn.execute("""
                    SELECT ap.project_id, p.name AS project_name FROM achievement_projects ap
                    JOIN projects p ON p.id=ap.project_id WHERE ap.achievement_id=?""", (r["id"],))]
        return ok(rows)
    d = body()
    if not d.get("title"):
        return fail("成果名称必填")
    with db() as conn:
        vals = [int(d.get(f, 0)) if f in ("funding_ack", "is_public") else d.get(f, "") for f in ACH_FIELDS]
        cur = conn.execute(f"INSERT INTO achievements({','.join(ACH_FIELDS)}) VALUES({','.join('?'*len(ACH_FIELDS))})", vals)
        aid = cur.lastrowid
        _sync_links(conn, aid, d)
    return ok({"id": aid}, message="成果已录入")


@app.route("/api/achievements/<int:aid>", methods=["GET", "PUT", "DELETE"])
def api_achievement(aid):
    with db() as conn:
        row = conn.execute("SELECT * FROM achievements WHERE id=?", (aid,)).fetchone()
        if not row:
            return fail("成果不存在", 404)
        if request.method == "GET":
            data = dict(row)
            data["indicators"] = [dict(x) for x in conn.execute(
                "SELECT * FROM achievement_indicators WHERE achievement_id=?", (aid,))]
            data["projects"] = [dict(x) for x in conn.execute(
                "SELECT * FROM achievement_projects WHERE achievement_id=?", (aid,))]
            return ok(data)
        if request.method == "DELETE":
            conn.execute("DELETE FROM achievements WHERE id=?", (aid,))
            return ok(message="已删除")
        d = body()
        sets, vals = [], []
        for f in ACH_FIELDS:
            if f in d:
                v = int(d[f]) if f in ("funding_ack", "is_public") else d[f]
                sets.append(f"{f}=?"); vals.append(v)
        if sets:
            sets.append("updated_at=datetime('now','localtime')")
            conn.execute(f"UPDATE achievements SET {','.join(sets)} WHERE id=?", vals + [aid])
        if "indicator_ids" in d or "project_ids" in d:
            _sync_links(conn, aid, d)
        return ok(message="已保存")


def _sync_links(conn, aid, d):
    """同步成果→指标、成果→项目关联（多对多）。"""
    if "indicator_ids" in d:
        conn.execute("DELETE FROM achievement_indicators WHERE achievement_id=?", (aid,))
        content_map = d.get("content_map", {}) or {}
        for iid in d["indicator_ids"]:
            if not iid:
                continue
            cid = content_map.get(str(iid)) or None
            conn.execute("INSERT OR IGNORE INTO achievement_indicators(achievement_id,indicator_id,content_id) VALUES(?,?,?)",
                         (aid, int(iid), int(cid) if cid else None))
    if "project_ids" in d:
        conn.execute("DELETE FROM achievement_projects WHERE achievement_id=?", (aid,))
        for pid in d["project_ids"]:
            if pid:
                conn.execute("INSERT OR IGNORE INTO achievement_projects(achievement_id,project_id) VALUES(?,?)",
                             (aid, int(pid)))


@app.route("/api/achievements/<int:aid>/attachment", methods=["POST"])
def api_ach_attachment(aid):
    """成果附件上传：保存文件到索引根目录，只回写相对路径与文件名。"""
    with db() as conn:
        if not conn.execute("SELECT 1 FROM achievements WHERE id=?", (aid,)).fetchone():
            return fail("成果不存在", 404)
        f = request.files.get("file")
        if not f or not f.filename:
            return fail("未选择文件")
        rel, original = save_upload(f, "attachments")
        conn.execute("UPDATE achievements SET file_path=?,file_name=?,updated_at=datetime('now','localtime') WHERE id=?",
                     (rel, original, aid))
    return ok({"file_path": rel, "file_name": original}, message="附件已上传")


@app.route("/api/achievements/<int:aid>/attachment/recognize", methods=["POST"])
def api_ach_attachment_recognize(aid):
    """需求4：读取成果已上传的附件，自动识别元数据，返回建议值供人工确认后填入。
    仅对 PDF 有效（其他格式文本层不可靠）；返回置信度说明，绝不自动写库。"""
    from parser import parse_pdf
    with db() as conn:
        row = conn.execute("SELECT file_path FROM achievements WHERE id=?", (aid,)).fetchone()
    if not row or not row["file_path"]:
        return fail("请先上传附件再识别")
    rel = row["file_path"]
    abs_path = rel if os.path.isabs(rel) else os.path.join(FILES_ROOT, rel)
    if not os.path.isfile(abs_path):
        return fail("附件文件不存在")
    if not abs_path.lower().endswith(".pdf"):
        return fail("自动识别目前仅支持 PDF（其他格式请手动填写，或先转为 PDF）")
    info = parse_pdf(abs_path)
    if info.get("error"):
        return fail(info["error"])
    suggestion = {k: info.get(k) for k in ("title", "authors", "journal", "pub_date", "identifier", "ach_type")}
    return ok({"suggestion": suggestion, "confidence": info.get("confidence", {}),
               "text_preview": info.get("text_preview", "")},
              message="识别完成，请核对后填入（不会自动保存）")


@app.route("/api/achievements/<int:aid>/attachment", methods=["DELETE"])
def api_ach_attachment_delete(aid):
    """移除成果附件索引（不删除原文件，避免误删）。"""
    with db() as conn:
        conn.execute("UPDATE achievements SET file_path='',file_name='',updated_at=datetime('now','localtime') WHERE id=?", (aid,))
    return ok(message="附件索引已移除（原文件保留）")


@app.route("/api/achievements/<int:aid>/archive", methods=["POST"])
def api_archive(aid):
    with db() as conn:
        row = conn.execute("SELECT * FROM achievements WHERE id=?", (aid,)).fetchone()
        if not row:
            return fail("成果不存在", 404)
        fp = row["file_path"] or ""
        abs_path = fp if os.path.isabs(fp) else os.path.join(FILES_ROOT, fp)
        if not os.path.isfile(abs_path):
            return fail("原始文件不存在，无法归档")
        rel = archive_file(abs_path, "归档")
        conn.execute("UPDATE achievements SET file_path=?,file_name=? WHERE id=?",
                     (rel, os.path.basename(abs_path), aid))
    return ok({"file_path": rel}, message="已归档到固定根目录")


# ---------- 扫描识别 ----------
@app.route("/api/scan", methods=["POST"])
def api_scan():
    d = body()
    folder = d.get("folder", "")
    res = scan_folder(folder, recursive=bool(d.get("recursive", True)))
    if not res.get("ok"):
        return fail(res.get("error", "扫描失败"))
    # 附加查重信息：已入库的文件指纹
    with db() as conn:
        existing = set()
        for r in conn.execute("SELECT file_name FROM achievements WHERE file_name != ''"):
            existing.add(r[0])
    for it in res["items"]:
        it["duplicate"] = it["file_name"] in existing
    return ok(res)


@app.route("/api/scan/commit", methods=["POST"])
def api_scan_commit():
    """批量确认入库：只创建成果记录 + 关联，不自动标记指标完成。"""
    d = body()
    items = d.get("items", [])
    if not items:
        return fail("没有待入库的成果")
    created = []
    with db() as conn:
        for it in items:
            if not it.get("title"):
                continue
            vals = [
                it.get("title", ""), it.get("ach_type", "期刊论文"), it.get("status", "已交付"),
                it.get("level", "普通"), it.get("authors", ""), it.get("journal", ""),
                it.get("pub_date", ""), it.get("identifier", ""), int(it.get("funding_ack", 0)),
                it.get("funding_code", ""), int(it.get("is_public", 1)),
                it.get("rel_path", "") or it.get("abs_path", ""), it.get("file_name", ""),
                "scan", it.get("note", ""),
            ]
            cur = conn.execute(f"INSERT INTO achievements({','.join(ACH_FIELDS)}) VALUES({','.join('?'*len(ACH_FIELDS))})", vals)
            aid = cur.lastrowid
            _sync_links(conn, aid, it)
            created.append(aid)
    return ok({"ids": created}, message=f"已入库 {len(created)} 条成果")


# ---------- 经费管理 ----------
def _sync_meta_budget(conn, pid):
    """财务预算科目变动后，用科目合计回写项目元信息经费总额，保持双向一致。"""
    total = conn.execute("SELECT COALESCE(SUM(budget),0) FROM budget_items WHERE project_id=?", (pid,)).fetchone()[0]
    conn.execute("UPDATE projects SET budget=?, updated_at=datetime('now','localtime') WHERE id=?", (round(total, 2), pid))
    return round(total, 2)


@app.route("/api/projects/<int:pid>/finance", methods=["GET"])
def api_finance(pid):
    with db() as conn:
        proj = conn.execute("SELECT budget, disbursed FROM projects WHERE id=?", (pid,)).fetchone()
        budget = [dict(r) for r in conn.execute("SELECT * FROM budget_items WHERE project_id=? ORDER BY id", (pid,))]
        expenses = [dict(r) for r in conn.execute("SELECT * FROM expenses WHERE project_id=? ORDER BY expense_date DESC,id DESC", (pid,))]
        for b in budget:
            b["spent"] = round(sum(e["amount"] or 0 for e in expenses if e.get("budget_item_id") == b["id"]), 2)
            b["rate"] = round(b["spent"] / b["budget"] * 100, 1) if b["budget"] else 0
            b["disbursed"] = 0  # 兼容旧字段；拨付已改为项目级单值
        total_b = sum(b["budget"] or 0 for b in budget)
        total_s = sum(e["amount"] or 0 for e in expenses)
        total_d = round(proj["disbursed"] or 0, 2) if proj else 0
    meta_budget = round(proj["budget"] or 0, 2) if proj else 0
    return ok({"budget": budget, "expenses": expenses,
               "meta_budget": meta_budget, "budget_total": round(total_b, 2),
               "in_sync": abs(meta_budget - total_b) < 0.01,
               "total_budget": total_b, "total_spent": round(total_s, 2),
               "total_disbursed": round(total_d, 2),
               "total_rate": round(total_s / total_b * 100, 1) if total_b else 0})


@app.route("/api/projects/<int:pid>/finance/disbursed", methods=["PUT"])
def api_finance_set_disbursed(pid):
    """录入项目级实际拨付金额：一个项目一个数，与预算科目、支出完全独立。
    body: {"amount": 数值}；兼容旧客户端 {"items": {...}}（按合计写入）。"""
    d = body()
    raw = d.get("amount", d.get("value"))
    if raw is None and isinstance(d.get("items"), dict):
        raw = sum(float(str(v or "").replace(",", "") or 0) for v in d["items"].values())
    amt = str(raw or "").replace(",", "").strip()
    try:
        val = float(amt) if amt else 0.0
    except ValueError:
        return fail("拨付金额格式无效")
    if val < 0:
        return fail("拨付金额不能为负数")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
            return fail("项目不存在", 404)
        conn.execute("UPDATE projects SET disbursed=?, updated_at=datetime('now','localtime') WHERE id=?",
                     (round(val, 2), pid))
    return ok({"total_disbursed": round(val, 2)}, message=f"实际拨付金额已录入：{round(val, 2)} 万")


@app.route("/api/projects/<int:pid>/budget", methods=["POST"])
def api_budget_add(pid):
    d = body()
    if not d.get("category"):
        return fail("预算科目必填")
    with db() as conn:
        cur = conn.execute("INSERT INTO budget_items(project_id,category,budget,note) VALUES(?,?,?,?)",
                           (pid, d["category"], float(d.get("budget") or 0), d.get("note", "")))
        total = _sync_meta_budget(conn, pid)
    return ok({"id": cur.lastrowid, "meta_budget": total}, message="已添加，元信息经费总额已同步")


@app.route("/api/budget/<int:bid>", methods=["PUT", "DELETE"])
def api_budget(bid):
    with db() as conn:
        item = conn.execute("SELECT project_id FROM budget_items WHERE id=?", (bid,)).fetchone()
        pid = item["project_id"] if item else None
        if request.method == "DELETE":
            conn.execute("DELETE FROM budget_items WHERE id=?", (bid,))
            if pid:
                _sync_meta_budget(conn, pid)
            return ok(message="已删除，元信息经费总额已同步")
        d = body()
        sets, vals = [], []
        for f in ("category", "budget", "note"):
            if f in d:
                if f == "budget":
                    raw = str(d[f] or "").replace(",", "").strip()
                    v = float(raw) if raw else 0.0
                else:
                    v = d[f]
                sets.append(f"{f}=?"); vals.append(v)
        if sets:
            conn.execute(f"UPDATE budget_items SET {','.join(sets)} WHERE id=?", vals + [bid])
        if pid:
            _sync_meta_budget(conn, pid)
    return ok(message="已保存，元信息经费总额已同步")


@app.route("/api/projects/<int:pid>/finance/sync-from-meta", methods=["POST"])
def api_finance_sync_from_meta(pid):
    """以项目元信息经费总额为准，强制同步预算科目（用于修复历史不一致数据）。"""
    with db() as conn:
        p = conn.execute("SELECT budget FROM projects WHERE id=?", (pid,)).fetchone()
        if not p:
            return fail("项目不存在", 404)
        info = sync_budget_from_meta(conn, pid, p["budget"])
    return ok(info, message=f"已按元信息经费 {info['total']} 万同步预算科目")


@app.route("/api/projects/<int:pid>/finance/import-excel", methods=["POST"])
def api_finance_import_excel(pid):
    """上传 Excel 经费表，自动解析为预算科目+支出流水；支出不再逐笔手工录入。
    兼容表头：科目/类别、预算/预算金额/金额、支出/已用/执行/实际支出、日期/时间、说明/备注、凭证。
    无表头时按列序：科目、预算、支出、日期、说明、凭证。
    实际拨付金额不随 Excel 导入，在经费看板单独录入项目级数值。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return fail("未选择 Excel 文件")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xlsm"):
        return fail("仅支持 .xlsx 格式 Excel（旧版 .xls 请先另存为 .xlsx）")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(f.stream, data_only=True, read_only=True)
        ws = wb.active
        raw = list(ws.iter_rows(values_only=True))
    except Exception as e:
        return fail("Excel 解析失败：" + str(e))
    if not raw:
        return fail("Excel 内容为空")

    def norm(x):
        return str(x).strip().replace(" ", "") if x is not None else ""

    header = [norm(c) for c in raw[0]]
    kw = {
        "category": ["科目", "类别", "名称", "项目"],
        "budget": ["预算", "总额", "计划", "额度"],
        "spent": ["支出", "已用", "执行", "实际支出"],
        "date": ["日期", "时间", "年月"],
        "detail": ["说明", "备注", "用途", "摘要"],
        "voucher": ["凭证", "单据", "票号"],
    }

    def find_col(keys):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return None

    has_header = any(find_col(v) is not None for v in kw.values())
    idx = {k: find_col(v) for k, v in kw.items()}
    if not has_header:
        idx = {"category": 0, "budget": 1, "spent": 2, "date": 3, "detail": 4, "voucher": 5}
    has_budget_col = idx.get("budget") is not None
    data_rows = raw[1:] if has_header else raw

    def cell(row, i):
        if i is None or i >= len(row) or row[i] is None:
            return ""
        v = row[i]
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        return str(v).strip()

    def num(row, i):
        v = cell(row, i)
        if not v:
            return 0.0
        try:
            return float(str(v).replace(",", ""))
        except ValueError:
            return 0.0

    added_budget = 0
    added_expense = 0
    skipped = 0
    with db() as conn:
        for row in data_rows:
            cat = cell(row, idx["category"])
            budget = num(row, idx["budget"])
            spent = num(row, idx["spent"])
            if not cat and not budget and not spent:
                skipped += 1
                continue
            if has_budget_col:
                if not cat:
                    cat = "未命名科目"
                cur = conn.execute("INSERT INTO budget_items(project_id,category,budget,note) VALUES(?,?,?,?)",
                                   (pid, cat, budget, "Excel导入"))
                bid = cur.lastrowid
                added_budget += 1
            else:
                # 纯支出表（无预算列）：能匹配到已有科目就挂上去，否则不强行造预算科目
                found = conn.execute(
                    "SELECT id FROM budget_items WHERE project_id=? AND category=? ORDER BY id LIMIT 1",
                    (pid, cat)).fetchone()
                bid = found["id"] if found else None
            if spent:
                conn.execute("""INSERT INTO expenses(project_id,budget_item_id,amount,expense_date,description,voucher)
                    VALUES(?,?,?,?,?,?)""",
                    (pid, bid, spent, cell(row, idx["date"]), cell(row, idx["detail"]), cell(row, idx["voucher"])))
                added_expense += 1
        total = _sync_meta_budget(conn, pid)
    return ok({"added_budget": added_budget, "added_expense": added_expense,
               "skipped": skipped, "meta_budget": total},
              message=f"已导入 {added_budget} 个科目、{added_expense} 条支出，元信息经费总额已同步为 {total} 万")


@app.route("/api/expenses/<int:eid>", methods=["DELETE"])
def api_expense_delete(eid):
    """仅用于更正误导入的支出记录；新增支出统一走 Excel 导入。"""
    with db() as conn:
        conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
    return ok(message="已删除")


# ---------- 结题导出 ----------
@app.route("/api/export/<int:pid>/<fmt>")
def api_export(pid, fmt):
    if fmt == "md":
        content = export_markdown(pid)
        return Response(content, mimetype="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''project_{pid}.md"})
    if fmt == "docx":
        data = export_docx(pid)
        return send_file(io.BytesIO(data), as_attachment=True,
                         download_name=f"结题素材汇编_项目{pid}.docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return fail("不支持的导出格式")


# ---------- 配置 ----------
@app.route("/api/config")
def api_config():
    return ok({"files_root": FILES_ROOT, "db_path": DB_PATH})


def pick_port(start=8765):
    """从 start 起找一个可用端口，避免双击 exe 时端口被占用导致启动失败。"""
    import socket
    for p in range(start, start + 20):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return start


if __name__ == "__main__":
    import webbrowser
    import threading
    port = pick_port()
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print("科研项目管理软件已启动")
    print("浏览器地址：" + url)
    print("数据库：" + DB_PATH)
    print("成果文件根目录：" + FILES_ROOT)
    print("关闭软件：直接关闭本窗口即可")
    print("=" * 60)
    # 延迟打开默认浏览器（服务起来后再打开）
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
