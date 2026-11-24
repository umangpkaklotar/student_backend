"""Interactive CLI script to create an admin account safely."""

import asyncio
import getpass
import sys

from pymongo.errors import DuplicateKeyError

from app.core.security import hash_password
from app.database.collections import users_collection
from app.database.connection import close_mongo_connection, connect_to_mongo
from app.models.user import build_user_document


async def create_admin_interactive() -> int:
    print("=== Create Admin Account ===")
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass.getpass("Admin password (min 6 chars): ").strip()
    confirm_password = getpass.getpass("Confirm password: ").strip()

    if len(name) < 2:
        print("Error: Admin name must be at least 2 characters.")
        return 1
    if "@" not in email or "." not in email:
        print("Error: Please enter a valid email address.")
        return 1
    if len(password) < 6:
        print("Error: Password must be at least 6 characters.")
        return 1
    if password != confirm_password:
        print("Error: Passwords do not match.")
        return 1

    await connect_to_mongo()
    try:
        existing = await users_collection().find_one({"email": email})
        if existing:
            print(f"Error: A user with email '{email}' already exists.")
            return 1

        user_doc = build_user_document(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            role="admin",
            email_verified=True,
            status_val="active",
        )
        result = await users_collection().insert_one(user_doc)
        print(f"Admin account created successfully! ID: {result.inserted_id}, Email: {email}")
        return 0
    except DuplicateKeyError:
        print(f"Error: A user with email '{email}' already exists.")
        return 1
    finally:
        await close_mongo_connection()


def main() -> None:
    exit_code = asyncio.run(create_admin_interactive())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
