"""
One-time data wipe for the EHS → CIDSA GIS migration.

Clears the old EHS knowledge base + chat history so the app starts fresh
for GIS books. PRESERVES users, companies, invites and allowlist.

Run: cd /app/backend && python wipe_corpus.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.db import (
    documents_col, web_sources_col, chat_sessions_col, chat_messages_col,
)


async def main():
    print("=== CIDSA GIS — wiping old EHS corpus ===")

    # 1. Delete uploaded files on disk
    docs = [d async for d in documents_col().find({}, {"_id": 0, "file_path": 1})]
    removed_files = 0
    for d in docs:
        fp = d.get("file_path")
        if fp:
            try:
                Path(fp).unlink(missing_ok=True)
                removed_files += 1
            except Exception:
                pass

    # 2. Drop Mongo collections' content (documents, web sources, chats)
    r_docs = await documents_col().delete_many({})
    r_web = await web_sources_col().delete_many({})
    r_msgs = await chat_messages_col().delete_many({})
    r_sess = await chat_sessions_col().delete_many({})

    # 3. Qdrant collections are reset separately via the admin API
    #    (/api/admin/qdrant/reset) because the running backend holds the
    #    local file-mode lock and a second client can't attach.
    print(f"  Documents deleted: {r_docs.deleted_count} ({removed_files} files removed from disk)")
    print(f"  Web sources deleted: {r_web.deleted_count}")
    print(f"  Chat sessions deleted: {r_sess.deleted_count}")
    print(f"  Chat messages deleted: {r_msgs.deleted_count}")
    print("=== Mongo wipe complete — now reset Qdrant via the admin API ===")


if __name__ == "__main__":
    asyncio.run(main())
