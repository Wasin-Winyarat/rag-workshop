"""แบ่งเอกสารเป็น chunk พร้อม metadata (เวิร์กช็อป 1)

แต่ละ chunk เป็น dict ที่มีอย่างน้อย:
chunk_id ("<doc_id>#<ลำดับ>"), doc_id, title, section, status, effective_date, text
"""
from rag.ingest import load_docs

MAX_CHARS = 600


def split_sections(body: str) -> list[tuple[str, list[str]]]:
    """คืน [(ชื่อหัวข้อ, บรรทัดเนื้อหา)] ตามหัวข้อ ## ข้ามหัวเรื่อง # และบรรทัดว่าง"""
    sections, name, lines = [], "", []
    for line in body.splitlines():
        if line.startswith("## "):
            if lines:
                sections.append((name, lines))
            name, lines = line[3:].strip(), []
        elif line.strip() and not line.startswith("# "):
            lines.append(line.strip())
    if lines:
        sections.append((name, lines))
    return sections


def pack_lines(header: str, lines: list[str], max_chars: int) -> list[str]:
    """รวมบรรทัดเป็นก้อนที่ยาวไม่เกิน max_chars ทุกก้อนขึ้นต้นด้วยชื่อหัวข้อ"""
    room = max_chars - len(header) - 1
    pieces = []
    for line in lines:  # บรรทัดที่ยาวเกินก้อนเดียวต้องตัดตามตัวอักษร
        pieces += [line[i:i + room] for i in range(0, len(line), room)]
    texts, cur = [], []
    for p in pieces:
        if cur and len("\n".join(cur + [p])) > room:
            texts.append(cur)
            cur = []
        cur.append(p)
    if cur:
        texts.append(cur)
    return [header + "\n" + "\n".join(t) for t in texts]


def chunk_docs(docs: list[dict] | None = None, max_chars: int = MAX_CHARS) -> list[dict]:
    docs = load_docs() if docs is None else docs
    chunks = []
    for d in docs:
        meta = {k: v for k, v in d.items() if k != "body"}
        n = 0
        for section, lines in split_sections(d["body"]):
            header = f"## {section}" if section else f"# {d['title']}"
            for text in pack_lines(header, lines, max_chars):
                n += 1
                chunks.append({**meta, "chunk_id": f"{d['doc_id']}#{n}", "section": section or d["title"], "text": text})
    return chunks


if __name__ == "__main__":
    cs = chunk_docs()
    print(len(cs), "chunks · ยาวสุด", max(len(c["text"]) for c in cs), "ตัวอักษร")
