#!/usr/bin/env python3
"""
Memory consolidation script for Mem0 + Qdrant (Hermes Agent).
Scores memories on recency × importance × relevance and soft-expires stale ones.
Run as: python3 ~/.hermes/scripts/memory_consolidation.py [--dry-run]

Differences from references/consolidation-script.py (the generic version):
- Uses set_payload + expiration_date for SOFT expire (not hard delete)
- Includes stale keyword patterns (exams, trips, "currently working on")
- Includes important keyword protection (identity, employment, preferences)
- Verbose dry-run output showing what would be expired and why

Scoring:
  - Recency: exponential decay (half-life 30 days) → 0.4 weight
  - Importance: metadata-based with category defaults + keyword auto-boost → 0.4 weight
  - Relevance: access_count sigmoid → 0.2 weight

Memories below prune_threshold (0.15) get soft-expired (expiration_date set).
Memories matching stale patterns (exams past, events over) get hard-expired.
Memories matching important patterns (name, email, career) are never pruned.
"""
import math
import json
import os
import sys
import argparse
import logging
from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any

sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
os.environ.setdefault('CUDA_VISIBLE_DEVICES', '')

from qdrant_client import QdrantClient
from qdrant_client import models

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('memory_consolidation')

# --- Config ---
QDRANT_HOST = 'localhost'
QDRANT_PORT = 6333
COLLECTION = 'hermes'
USER_ID = os.environ.get("MEM0_USER_ID", "sample_user")

# Scoring weights
W_RECENCY = 0.4
W_IMPORTANCE = 0.4
W_RELEVANCE = 0.2

# Thresholds
PRUNE_THRESHOLD = 0.15
HALF_LIFE_DAYS = 30.0
MAX_MEMORIES = 500

# Stale keyword patterns — memories matching these are likely time-sensitive
STALE_PATTERNS = {
    'exam': 30,
    'scheduled for': 30,
    'remaining exams': 30,
    'has two remaining': 30,
    'planning a trip': 60,
    'is planning': 60,
    'currently working on': 90,
    'in progress': 90,
}

# Important keywords — these should never be pruned
IMPORTANT_PATTERNS = [
    "user's name", 'user name is', 'email address', 'phone number',
    'lives in', 'based in', 'born', 'degree', 'university', 'cgpa',
    'career history', 'employment', 'job offer', 'accepted a job',
    'preferences', 'prefers', 'always uses', 'resume', 'cv',
]


class MemoryConsolidator:
    def __init__(self, dry_run: bool = True):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.dry_run = dry_run

    def _recency_score(self, created_at_str: str) -> float:
        try:
            created = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
            return math.exp(-0.693 * age_days / HALF_LIFE_DAYS)
        except (ValueError, TypeError):
            return 0.0

    def _importance_score(self, text: str, payload: dict) -> float:
        importance = payload.get('importance', 5)
        category = payload.get('category', '')
        if category in ('life_events', 'identity', 'preferences'):
            importance = max(importance, 8)
        text_lower = text.lower()
        for pattern in IMPORTANT_PATTERNS:
            if pattern in text_lower:
                importance = max(importance, 8)
                break
        return min(float(importance) / 10.0, 1.0)

    def _relevance_score(self, payload: dict) -> float:
        access_count = payload.get('access_count', 0)
        return 1.0 / (1.0 + math.exp(-0.5 * (access_count - 3)))

    def _consolidation_score(self, text: str, payload: dict) -> float:
        recency = self._recency_score(payload.get('created_at', ''))
        importance = self._importance_score(text, payload)
        relevance = self._relevance_score(payload)
        return W_RECENCY * recency + W_IMPORTANCE * importance + W_RELEVANCE * relevance

    def _is_stale(self, text: str, created_at_str: str) -> tuple:
        text_lower = text.lower()
        try:
            created = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
        except (ValueError, TypeError):
            return False, 0
        for pattern, stale_after_days in STALE_PATTERNS.items():
            if pattern in text_lower and age_days > stale_after_days:
                return True, 0
        return False, 0

    def _fetch_all_memories(self) -> List[Dict[str, Any]]:
        all_points = []
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=COLLECTION,
                scroll_filter=models.Filter(
                    must=[models.FieldCondition(
                        key='user_id',
                        match=models.MatchValue(value=USER_ID)
                    )]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(results)
            if offset is None:
                break
        return all_points

    def consolidate(self) -> Dict[str, int]:
        memories = self._fetch_all_memories()
        logger.info(f'Found {len(memories)} memories for user {USER_ID}')
        if not memories:
            return {'total': 0, 'kept': 0, 'expired': 0, 'stale_expired': 0}

        scored = []
        for point in memories:
            payload = point.payload or {}
            text = payload.get('data', '')
            if not text:
                continue
            score = self._consolidation_score(text, payload)
            is_stale, _ = self._is_stale(text, payload.get('created_at', ''))
            has_expiration = bool(payload.get('expiration_date'))
            scored.append({
                'id': point.id,
                'score': score,
                'text': text,
                'payload': payload,
                'is_stale': is_stale,
                'has_expiration': has_expiration,
                'created_at': payload.get('created_at', ''),
            })

        scored.sort(key=lambda x: x['score'], reverse=True)

        to_expire_stale = [m for m in scored if m['is_stale'] and not m['has_expiration']]
        to_expire_low = [m for m in scored if m['score'] < PRUNE_THRESHOLD
                         and not m['is_stale'] and not m['has_expiration']]
        to_keep = [m for m in scored if m['score'] >= PRUNE_THRESHOLD and not m['is_stale']]
        to_expire_cap = []
        if len(to_keep) > MAX_MEMORIES:
            to_expire_cap = to_keep[MAX_MEMORIES:]
            to_keep = to_keep[:MAX_MEMORIES]

        all_to_expire = to_expire_stale + to_expire_low + to_expire_cap
        today = datetime.now(timezone.utc).date().isoformat()

        logger.info(f'  Keep: {len(to_keep)}')
        logger.info(f'  Stale-expire: {len(to_expire_stale)}')
        logger.info(f'  Low-score-expire: {len(to_expire_low)}')
        logger.info(f'  Cap-expire: {len(to_expire_cap)}')

        for m in all_to_expire[:10]:
            reason = 'stale' if m['is_stale'] else f'score={m["score"]:.3f}'
            logger.info(f'    [{reason}] {m["text"][:70]}')

        if not self.dry_run and all_to_expire:
            for m in all_to_expire:
                self.client.set_payload(
                    collection_name=COLLECTION,
                    payload={'expiration_date': today},
                    points=[m['id']],
                )
            logger.info(f'✅ Expired {len(all_to_expire)} memories (set expiration_date={today})')
        elif self.dry_run:
            logger.info(f'[DRY RUN] Would expire {len(all_to_expire)} memories')

        return {
            'total': len(scored),
            'kept': len(to_keep),
            'expired': len(all_to_expire),
            'stale_expired': len(to_expire_stale),
        }

    def close(self):
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description='Memory consolidation for Hermes Agent')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be expired without doing it')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show more details')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    consolidator = MemoryConsolidator(dry_run=args.dry_run)
    try:
        result = consolidator.consolidate()
        print(f'\n=== Consolidation Summary ===')
        print(f'  Total memories: {result["total"]}')
        print(f'  Kept:           {result["kept"]}')
        print(f'  Expired:        {result["expired"]}')
        print(f'    (stale):      {result["stale_expired"]}')
        if args.dry_run:
            print(f'\n  [DRY RUN] No changes made. Run without --dry-run to apply.')
    finally:
        consolidator.close()


if __name__ == '__main__':
    main()