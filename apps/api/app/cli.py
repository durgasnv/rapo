"""Trusted server-side administration; never exposed as an HTTP endpoint."""

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import make_engine
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant organizer access to an existing account")
    parser.add_argument("email")
    arguments = parser.parse_args()
    engine = make_engine(Settings().database_url)
    try:
        with Session(engine) as db, db.begin():
            user = db.scalar(select(User).where(User.email == arguments.email.strip().lower()))
            if user is None:
                parser.error("Create the account before granting organizer access")
            user.role = "organizer"
        print("Organizer access granted.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
