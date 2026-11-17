"""Standalone migration execution script for deployment pipelines (P1-LIM-011).

Executes Alembic database migrations as a decoupled deployment step,
preventing concurrent schema mutation races across multiple application replicas.
"""

import argparse
import logging
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("corbel.migrate")


def run_migrations(target_revision: str = "head") -> None:
    """Execute Alembic migrations to the specified target revision."""
    root_dir = Path(__file__).resolve().parent.parent
    alembic_ini_path = root_dir / "alembic.ini"

    if not alembic_ini_path.exists():
        logger.error(f"alembic.ini not found at expected path: {alembic_ini_path}")
        sys.exit(1)

    logger.info(f"Loading Alembic configuration from {alembic_ini_path}")
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(root_dir / "alembic"))

    logger.info(f"Executing database migration to target revision '{target_revision}'...")
    try:
        command.upgrade(alembic_cfg, target_revision)
        logger.info(f"Successfully applied migrations up to '{target_revision}'.")
    except Exception as exc:
        logger.error(f"Migration failed: {exc}", exc_info=True)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Corbel Database Migration Runner")
    parser.add_argument(
        "--revision",
        default="head",
        help="Target migration revision (default: head)",
    )
    args = parser.parse_args()
    run_migrations(args.revision)


if __name__ == "__main__":
    main()
