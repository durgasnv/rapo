"""Trusted local-only import command for the college demo dataset."""

import argparse
import getpass
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import make_engine
from app.schemas.dataset import Dataset
from app.services.dataset_import import import_dataset, member_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect the college dataset to a local rapo DB")
    parser.add_argument("--organizer", required=True, help="Existing organizer email")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "demo/dataset_college.json",
    )
    parser.add_argument("--namespace", default="college")
    parser.add_argument("--shift-days", type=int, default=0, help="Explicitly shift every schedule")
    parser.add_argument(
        "--check", action="store_true", help="Validate JSON without database writes"
    )
    args = parser.parse_args()
    try:
        dataset = Dataset.model_validate_json(args.file.read_text())
        if args.check:
            print(
                f"Validated {len(dataset.events)} events "
                f"and {len(dataset.members)} source profiles."
            )
            return
        config = Settings()
        url = make_url(config.database_url)
        if (
            config.environment != "development"
            or url.get_backend_name() != "postgresql"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("College imports require a local development PostgreSQL database")
        password = os.environ.get("RAPO_DEMO_PASSWORD")
        if password is None:
            password = getpass.getpass("Password for synthetic participants (12–128 characters): ")
        engine = make_engine(config.database_url)
        try:
            with Session(engine) as db, db.begin():
                result = import_dataset(
                    db,
                    dataset,
                    args.organizer,
                    args.namespace,
                    password,
                    shift_days=args.shift_days,
                )
        finally:
            engine.dispose()
        print(
            "College dataset imported."
            if result.created
            else "Already imported; UI edits preserved."
        )
        print(
            f"Participants: {result.participants}; "
            f"cancelled dropout registrations: {result.cancelled_registrations}"
        )
        for source_id, event_id in result.event_ids.items():
            print(f"{source_id}: /organizer/events/{event_id}")
        first = next(m for m in dataset.members if m.role == "participant")
        print(f"Participant login: {member_email(args.namespace, first.id)}")
        print("Use the demo password supplied on the first import.")
    except ValidationError as error:
        parser.error(
            "Dataset validation failed: "
            + "; ".join(
                f"{'.'.join(map(str, item['loc'])) or 'dataset'}: {item['msg']}"
                for item in error.errors(include_input=False)
            )
        )
    except ValueError as error:
        parser.error(str(error))
    except (OSError, SQLAlchemyError):
        parser.exit(1, "Import failed. Check the local database, migrations and dataset file.\n")


if __name__ == "__main__":
    main()
