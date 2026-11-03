"""Basic PostgreSQL connection test."""

from database_utilities.database_connection import get_connection


def main() -> None:
    """Verify the database connection and print basic information."""

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), current_schema()"
            )

            database_name, schema_name = cursor.fetchone()

            print("Database connection successful.")
            print(f"Database: {database_name}")
            print(f"Schema: {schema_name}")


if __name__ == "__main__":
    main()