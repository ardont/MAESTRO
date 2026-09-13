import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup")

sys.path.insert(0, '/app/RLT_project')
sys.path.insert(0, '/app')

from rag.indexer.qdrant_indexer import get_qdrant_client
from rag.indexer.config import COLLECTION_NAME

def cleanup_roseltorg():
    client = get_qdrant_client()
    logger.info(f"Connecting to Qdrant collection '{COLLECTION_NAME}'...")
    
    total_checked = 0
    to_delete_ids = []
    next_offset = None
    
    while True:
        records, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=500,
            offset=next_offset,
            with_payload=True,
            with_vectors=False
        )
        if not records:
            break
            
        for r in records:
            total_checked += 1
            pl = r.payload or {}
            url = str(pl.get("url", "")).lower()
            title = str(pl.get("title", "")).lower()
            sec = str(pl.get("section_header", "")).lower()
            
            if "roseltorg" in url or "roseltorg" in title or "roseltorg" in sec or "source url:" in title or "source url:" in sec:
                to_delete_ids.append(r.id)
                
        logger.info(f"Checked {total_checked} points, marked for deletion: {len(to_delete_ids)}")
        if next_offset is None:
            break
            
    if to_delete_ids:
        logger.info(f"Deleting {len(to_delete_ids)} roseltorg points from Qdrant...")
        for i in range(0, len(to_delete_ids), 500):
            batch = to_delete_ids[i:i+500]
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=batch
            )
        logger.info(f"Successfully deleted {len(to_delete_ids)} dirty points.")
    else:
        logger.info("No roseltorg points found in collection.")

if __name__ == "__main__":
    cleanup_roseltorg()
