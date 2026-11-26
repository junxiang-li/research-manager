# -*- coding: utf-8 -*-
"""数据库层：SQLite schema 与连接管理。

三层架构：项目库(projects) — 指标库(research_contents / indicators，隶属于项目) — 成果库(achievements，全局)
成果与指标、成果与项目均为多对多关联，不从属。
"""
import os
import sys
import sqlite3
from contextlib import contextmanager

# 打包为 exe 后，数据目录跟随 exe 所在目录（保证复用已录入的数据，不随临时解压目录丢失）
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "research.db")

# 成果文件固定根目录：数据库只存相对该目录的路径。
# 可用环境变量 RESEARCH_FILES_ROOT 覆盖，换电脑时保证目录结构一致即可。
FILES_ROOT = os.environ.get("RESEARCH_FILES_ROOT") or os.path.join(DATA_DIR, "files")
FILES_ROOT = os.path.abspath(FILES_ROOT)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FILES_ROOT, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows_to_list(rows):
    return [dict(r) for r in rows]


SCHEMA = r"""
-- ========== 项目库 ==========
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT DEFAULT '',
    source TEXT DEFAULT '',
    leader TEXT DEFAULT '',
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    budget REAL DEFAULT 0,
    disbursed REAL DEFAULT 0,           -- 实际拨付金额（万元），项目级单值，与预算科目无关
    partners TEXT DEFAULT '',
    note TEXT DEFAULT '',
    status TEXT DEFAULT '在研',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 项目文档 / 基准快照版本（申报书、任务书、变更批复等）
CREATE TABLE IF NOT EXISTS project_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    doc_type TEXT NOT NULL,
    title TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    file_name TEXT DEFAULT '',
    is_baseline INTEGER DEFAULT 0,
    version_tag TEXT DEFAULT '',
    change_date TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    uploaded_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ========== 指标库（隶属于项目） ==========
-- 第一层：研究内容（大纲级，来自申报书，偏定性）
CREATE TABLE IF NOT EXISTS research_contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    order_num INTEGER DEFAULT 0,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- 第二层：考核指标（可考核、可量化，来自任务书）
CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    content_id INTEGER,
    title TEXT NOT NULL,
    ind_type TEXT DEFAULT 'quantitative',   -- quantitative 定量 / qualitative 定性
    target_value REAL DEFAULT 1,
    unit TEXT DEFAULT '',
    deadline TEXT DEFAULT '',
    weight REAL DEFAULT 0,                  -- 权重(%)，用于权重模式
    progress_mode TEXT DEFAULT 'count',     -- count 计数 / weight 权重（项目层聚合用）
    description TEXT DEFAULT '',
    manual_done INTEGER DEFAULT 0,          -- 定性指标手动完成标记
    order_num INTEGER DEFAULT 0,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(content_id) REFERENCES research_contents(id) ON DELETE SET NULL
);

-- ========== 成果库（全局，独立） ==========
CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    ach_type TEXT NOT NULL,
    status TEXT DEFAULT '已交付',       -- 在投/受理/录用/授权/已交付
    level TEXT DEFAULT '普通',          -- TOP期刊/核心/普通
    authors TEXT DEFAULT '',
    journal TEXT DEFAULT '',
    pub_date TEXT DEFAULT '',
    identifier TEXT DEFAULT '',         -- DOI / 专利号 / 标准号
    funding_ack INTEGER DEFAULT 0,      -- 是否标注项目资助号（结题审查重点）
    funding_code TEXT DEFAULT '',
    is_public INTEGER DEFAULT 1,        -- 是否对外公开
    file_path TEXT DEFAULT '',          -- 相对 FILES_ROOT 的路径（不存绝对路径）
    file_name TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',       -- manual 手动 / scan 扫描识别
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);

-- 成果 → 考核指标（多对多；一条成果可支撑多个指标，一个指标可由多条成果支撑）
CREATE TABLE IF NOT EXISTS achievement_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    achievement_id INTEGER NOT NULL,
    indicator_id INTEGER NOT NULL,
    content_id INTEGER,                 -- 同时标记支撑的研究内容
    UNIQUE(achievement_id, indicator_id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id) ON DELETE CASCADE,
    FOREIGN KEY(indicator_id) REFERENCES indicators(id) ON DELETE CASCADE
);

-- 成果 → 项目（多对多；一篇论文支撑两个项目是常态）
CREATE TABLE IF NOT EXISTS achievement_projects (
    achievement_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    PRIMARY KEY(achievement_id, project_id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- ========== 经费管理 ==========
CREATE TABLE IF NOT EXISTS budget_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    category TEXT NOT NULL,             -- 设备费/材料费/测试化验加工费/差旅费/劳务费/间接费用…
    budget REAL DEFAULT 0,
    disbursed REAL DEFAULT 0,           -- 历史字段：已弃用，保留仅为兼容旧库，不再读写
    note TEXT DEFAULT '',
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    budget_item_id INTEGER,
    amount REAL DEFAULT 0,
    expense_date TEXT DEFAULT '',
    description TEXT DEFAULT '',
    voucher TEXT DEFAULT '',
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(budget_item_id) REFERENCES budget_items(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ind_project ON indicators(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_ind ON achievement_indicators(indicator_id);
CREATE INDEX IF NOT EXISTS idx_ai_ach ON achievement_indicators(achievement_id);
CREATE INDEX IF NOT EXISTS idx_ap_project ON achievement_projects(project_id);
"""


def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        # 旧版本数据库平滑升级：只加列、不改动任何已有数据
        cols = {r[1] for r in conn.execute("PRAGMA table_info(budget_items)")}
        if "disbursed" not in cols:
            conn.execute("ALTER TABLE budget_items ADD COLUMN disbursed REAL DEFAULT 0")
        # 项目级拨付金额：首次升级时把旧版按科目登记的拨付金额汇总过来，避免历史数据丢失
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "disbursed" not in pcols:
            conn.execute("ALTER TABLE projects ADD COLUMN disbursed REAL DEFAULT 0")
            conn.execute("""UPDATE projects
                            SET disbursed = COALESCE((
                                SELECT SUM(budget_items.disbursed) FROM budget_items
                                WHERE budget_items.project_id = projects.id), 0)""")
    return DB_PATH


if __name__ == "__main__":
    init_db()
    print("DB initialized:", DB_PATH)
    print("FILES_ROOT:", FILES_ROOT)
