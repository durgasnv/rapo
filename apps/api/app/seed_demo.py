"""Trusted local demo command; never exposed as an HTTP endpoint."""

import argparse
import getpass
import os

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import make_engine
from app.services.demo_data import member_email, seed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create repeatable synthetic large-event demo data"
    )
    parser.add_argument("--organizer", required=True, help="Existing organizer email")
    parser.add_argument(
        "--namespace", default="large-demo", help="New name for an independent demo"
    )
    arguments = parser.parse_args()
    password = os.environ.get("RAPO_DEMO_PASSWORD")
    if password is None:
        password = getpass.getpass("Password for synthetic members (12–128 characters): ")
    engine = make_engine(Settings().database_url)
    try:
        with Session(engine) as db, db.begin():
            result = seed(db, arguments.organizer, arguments.namespace, password)
        print("Demo created." if result.created else "Demo already exists; UI changes preserved.")
        print(f"Grouping: /organizer/events/{result.scheduled_event_id}")
        print(f"Roster repair: /organizer/events/{result.roster_event_id}")
        print(f"Participant: {member_email(result.namespace, 1)}")
        print(f"First waitlisted member: {member_email(result.namespace, 101)}")
        print("Sign in with the demo password supplied on the first run.")
    except ValueError as error:
        parser.error(str(error))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
