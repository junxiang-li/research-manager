# -*- coding: utf-8 -*-
"""文件解析：PDF 元数据/首页解析 + 文件夹扫描。

边界说明：自动识别只做「自动填充表单」，绝不由系统自动判定成果已完成指标。
所有识别结果都必须经人工确认后入库（识别置信度随结果返回，供人工判断）。
"""
import os
import re
import hashlib
from datetime import datetime

from db import FILES_ROOT

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

SUPPORTED_EXT = {".pdf": "PDF", ".doc": "DOC", ".docx": "DOCX",
                 ".txt": "TXT", ".png": "图片", ".jpg": "图片", ".jpeg": "图片"}

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+", re.I)
PATENT_RE = re.compile(r"(?:CN|ZL)\s?\d{9,13}\s?[A-Z]?|CN\d{10,13}[A-Z]", re.I)
YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")
AUTHOR_LINE_RE = re.compile(r"^(作者|作\s*者|Authors?|By)\s*[:：]?\s*(.+)$", re.I)
JOURNAL_HINT = re.compile(r"(学报|期刊|杂志|Transactions|Journal|IEEE|ACM|Science|Nature|Press|Vol\.|Volume|第\s*\d+\s*卷)", re.I)


def to_rel_path(abs_path):
    """把绝对路径转成相对 FILES_ROOT 的路径；不在根目录内则返回 None。"""
    try:
        p = os.path.abspath(abs_path)
        rel = os.path.relpath(p, FILES_ROOT)
        if rel.startswith(".."):
            return None
        return rel.replace("\\", "/")
    except Exception:
        return None


def file_fingerprint(abs_path):
    """文件指纹（前 1MB 内容哈希），用于查重。"""
    try:
        h = hashlib.sha256()
        with open(abs_path, "rb") as f:
            h.update(f.read(1024 * 1024))
        return h.hexdigest()[:16]
    except Exception:
        return ""


def _pick_title(lines, meta_title):
    """从首页文本里猜标题：优先元数据，其次取前若干行中最像标题的一行。"""
    if meta_title and len(meta_title.strip()) > 4 and "microsoft" not in meta_title.lower():
        return meta_title.strip(), "元数据"
    candidates = []
    for i, ln in enumerate(lines[:12]):
        s = ln.strip()
        if not s or len(s) < 6 or len(s) > 120:
            continue
        if re.match(r"^(收稿|基金|摘要|Abstract|目录|DOI|中图分类号|文章编号)", s, re.I):
            continue
        # 标题通常不含大量标点结尾，且中文/英文混排
        score = len(s) - (40 if s.endswith(("。", "，", ".", ",")) else 0)
        candidates.append((score, i, s))
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][2], "首页启发式"
    return "", "未识别"


def _pick_authors(lines, meta_author):
    if meta_author and meta_author.strip():
        return meta_author.strip(), "元数据"
    for ln in lines[:15]:
        m = AUTHOR_LINE_RE.match(ln.strip())
        if m and m.group(2):
            return m.group(2).strip(), "首页启发式"
    return "", "未识别"


def _pick_journal(lines, meta_journal):
    if meta_journal and meta_journal.strip():
        return meta_journal.strip(), "元数据"
    for ln in lines[:15]:
        s = ln.strip()
        if 2 < len(s) < 80 and JOURNAL_HINT.search(s):
            return s, "首页启发式"
    return "", "未识别"


def guess_ach_type(filename, text):
    """根据文件名与文本猜成果类型（仅预填，人工可改）。"""
    blob = (filename + " " + text[:1500]).lower()
    # 更具体的类型优先，避免被后面的通用关键词抢先命中
    if "国际会议参会" in blob or "国际会议" in blob or "参会" in blob:
        return "国际会议参会"
    if "科普宣讲" in blob or "科普讲座" in blob or "科普报告" in blob:
        return "科普宣讲"
    if "科普文章" in blob or "科普" in blob:
        return "科普文章"
    if PATENT_RE.search(blob) or "专利" in blob or "patent" in blob:
        return "发明专利"
    if "学位" in blob or "thesis" in blob or "dissertation" in blob:
        return "研究生学位论文"
    if "报告" in blob or "report" in blob:
        return "试验报告"
    if "标准" in blob or "standard" in blob or "gb/t" in blob:
        return "标准"
    if "会议" in blob or "conference" in blob or "proceedings" in blob:
        return "会议论文"
    if "软著" in blob or "软件著作" in blob:
        return "软件著作权"
    return "期刊论文"


def parse_pdf(abs_path):
    """解析单个 PDF，返回识别字段 + 置信度说明。失败时返回 error。"""
    result = {
        "file_name": os.path.basename(abs_path),
        "abs_path": abs_path,
        "rel_path": to_rel_path(abs_path),
        "in_root": to_rel_path(abs_path) is not None,
        "fingerprint": file_fingerprint(abs_path),
        "title": "", "authors": "", "journal": "", "pub_date": "",
        "identifier": "", "ach_type": "", "year": "",
        "confidence": {}, "error": "",
    }
    if PdfReader is None:
        result["error"] = "缺少 pypdf 库"
        return result
    try:
        reader = PdfReader(abs_path)
        meta = reader.metadata or {}
        meta_title = meta.get("/Title") or ""
        meta_author = meta.get("/Author") or ""
        meta_journal = meta.get("/Subject") or ""
        meta_date = meta.get("/CreationDate") or ""

        text = ""
        if reader.pages:
            text = reader.pages[0].extract_text() or ""
        lines = [ln for ln in text.splitlines() if ln.strip()]

        title, tc = _pick_title(lines, meta_title)
        authors, ac = _pick_authors(lines, meta_author)
        journal, jc = _pick_journal(lines, meta_journal)

        doi = DOI_RE.search(text) or DOI_RE.search(meta_title + " " + meta_journal)
        patent = PATENT_RE.search(text)
        identifier = ""
        if patent:
            identifier = patent.group(0).strip()
        elif doi:
            identifier = "DOI: " + doi.group(0).rstrip(".，,;；")

        year = ""
        if meta_date:
            my = YEAR_RE.search(str(meta_date))
            if my:
                year = my.group(1)
        if not year:
            # 首页里找年份，优先靠后的（发表年常在页首下方或页脚）
            years = YEAR_RE.findall(text[:2500])
            if years:
                year = years[-1]

        result.update({
            "title": title,
            "authors": authors,
            "journal": journal,
            "pub_date": year,
            "year": year,
            "identifier": identifier,
            "ach_type": guess_ach_type(os.path.basename(abs_path), text),
            "confidence": {
                "title": tc, "authors": ac, "journal": jc,
                "identifier": "正则" if identifier else "未识别",
                "pub_date": "元数据/正则" if year else "未识别",
            },
            "text_preview": re.sub(r"\s+", " ", text[:400]).strip(),
        })
    except Exception as e:
        result["error"] = f"解析失败：{e}"
    return result


def scan_folder(folder_path, recursive=True, max_files=500):
    """扫描文件夹，返回待确认的成果识别列表（不入库、不拷贝文件）。"""
    if not folder_path or not os.path.isdir(folder_path):
        return {"ok": False, "error": "文件夹不存在或不可访问", "items": []}
    items, seen = [], set()
    root = os.path.abspath(folder_path)
    for dirpath, dirnames, filenames in os.walk(root):
        if not recursive:
            dirnames[:] = []
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SUPPORTED_EXT:
                continue
            abs_path = os.path.join(dirpath, fn)
            fp = file_fingerprint(abs_path)
            if fp and fp in seen:
                continue
            if fp:
                seen.add(fp)
            if ext == ".pdf":
                info = parse_pdf(abs_path)
            else:
                info = {
                    "file_name": fn, "abs_path": abs_path,
                    "rel_path": to_rel_path(abs_path),
                    "in_root": to_rel_path(abs_path) is not None,
                    "fingerprint": fp, "title": os.path.splitext(fn)[0],
                    "authors": "", "journal": "", "pub_date": "",
                    "identifier": "", "ach_type": guess_ach_type(fn, ""),
                    "confidence": {"title": "文件名"}, "error": "", "text_preview": "",
                }
            info["file_type"] = SUPPORTED_EXT[ext]
            items.append(info)
            if len(items) >= max_files:
                break
        if len(items) >= max_files:
            break
    return {"ok": True, "root": root, "count": len(items), "items": items}


def archive_file(abs_path, subdir="归档"):
    """把根目录外的文件复制进固定根目录并更新相对路径（用户主动选择时）。"""
    import shutil
    rel = to_rel_path(abs_path)
    if rel:
        return rel
    dest_dir = os.path.join(FILES_ROOT, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(abs_path)
    dest = os.path.join(dest_dir, name)
    i = 1
    while os.path.exists(dest):
        stem, ext = os.path.splitext(name)
        dest = os.path.join(dest_dir, f"{stem}_{i}{ext}")
        i += 1
    shutil.copy2(abs_path, dest)
    return to_rel_path(dest)
