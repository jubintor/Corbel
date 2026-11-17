"""Maintenance CLI script to purge expired sessions, refresh tokens, and stale rate limit buckets (P2-LIM-006).

Usage:
    python scripts/purge_auth_records.py [--retention-days 30] [--batch-size 1000]
"""

import argparse
import asyncio
import sys

from corbel.core.config import get_settings
from corbel.core.database import get_session_factory
from corbel.domains.tenancy.service import TenancyService


async def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Purge expired tokens, sessions, and rate-limit buckets outside retention window."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=settings.AUTH_SESSION_RETENTION_DAYS,
        help=f"Days to retain expired/revoked sessions (default: {settings.AUTH_SESSION_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.AUTH_TOKEN_PURGE_BATCH_SIZE,
        help=f"Maximum records to purge per entity type (default: {settings.AUTH_TOKEN_PURGE_BATCH_SIZE})",
    )
    args = parser.parse_args()

    print(f"[*] Starting auth records purge (retention_days={args.retention_days}, batch_size={args.batch_size})...")

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)
        stats = await service.purge_expired_records(
            retention_days=args.retention_days,
            batch_size=args.batch_size,
        )

    print("[+] Purge completed successfully:")
    print(f"    - Expired tokens purged: {stats.get('tokens_purged', 0)}")
    print(f"    - Expired sessions purged: {stats.get('sessions_purged', 0)}")
    print(f"    - Stale rate-limit buckets purged: {stats.get('buckets_purged', 0)}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
