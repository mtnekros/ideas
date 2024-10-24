"""Module holds functions to test different join query plans."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from textwrap import dedent
from typing import Dict

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=(
        logging.StreamHandler(),
        logging.FileHandler(filename="query_planner_test.log"),
    ),
)

DB_CREDS = {
    "host": "localhost",
    "user": "postgres",
    "password": "postgres",
    "database": "postgres",
    "port": 5432,
}

@contextmanager
def db_cursor() -> Iterator[psycopg2.extensions.cursor]:
    """Yield db cursor."""
    with psycopg2.connect(**DB_CREDS) as conn, conn.cursor() as cursor:
        yield cursor

def get_query_plan(query: str) -> str:
    """Return the query plan of the query."""
    query = f"""
    EXPLAIN ANALYZE {query}
    """
    with db_cursor() as cursor:
        cursor.execute(query)
        return "\n".join(row[0] for row in cursor.fetchall())

def create_table(table: str, columns: Dict[str, str]) -> None:
    """Create table with given name & columns."""
    sql_columns = ", ".join(f"{name} {_type}" for name,_type in columns.items())
    query = dedent(f"""
    DROP TABLE IF EXISTS {table};
    CREATE TABLE IF NOT EXISTS {table} (
        {sql_columns}
    );
    """)
    with db_cursor() as cursor:
        cursor.execute(query)

def get_sql_value_generator(sql_data_type: str) -> str:
    """Get a random sql value generator for given data type."""
    return {
        "text": "LEFT(MD5(random()::text), 10)",
        "int": "FLOOR(RANDOM()*10000000)",
    }[sql_data_type]

def insert_data_into_table(table: str, columns: Dict[str,str], row_count: int) -> None:
    """Truncate and add random data to existing table."""
    columns_filtered = {
        name: _type for name,_type in columns.items()
        if _type.strip().lower() != "serial"
    }
    sql_columns = ", ".join({name for name in columns_filtered})
    sql_column_generator = ", ".join(
        f"{get_sql_value_generator(_type)} AS {name}"
        for name, _type in columns_filtered.items()
    )
    query = f"""
    INSERT INTO {table} ({sql_columns})
    SELECT {sql_column_generator}
    FROM GENERATE_SERIES(1, {row_count});
    ANALYZE {table};
    """  # noqa: S608
    with db_cursor() as cursor:
        cursor.execute(query)

def add_indexes(index_on_t1: bool, index_on_t2: bool) -> None:
    """Add indexes to t1 & t2 table on id column based on passed parameters."""
    if not index_on_t1 and not index_on_t2:
        return
    with db_cursor() as cursor:
        if index_on_t1:
            cursor.execute(dedent("""
                DROP INDEX IF EXISTS t1_id_idx;
                CREATE INDEX t1_id_idx ON t1(id);
                CLUSTER t1 USING t1_id_idx;
            """))
        if index_on_t2:
            cursor.execute(dedent("""
                DROP INDEX IF EXISTS t2_id_idx;
                CREATE INDEX t2_id_idx ON t2(id);
                CLUSTER t2 USING t2_id_idx;
            """))
        cursor.execute("ANALYZE t1, t2;")

def run_tests() -> None:
    """Log query plan for join of different sizes of table."""
    tables = {
        "t1": {
            "id": "serial",
            "name": "text",
        },
        "t2": {
            "id": "serial",
            "name": "text"
        },
    }
    t1_sizes = t2_sizes = [1, 100, 10_000, 1_000_000 ] # , 1_000, 100_000, 1_000_000, 5_000_000]
    queries = [
        """SELECT * FROM t1 INNER JOIN t2 ON t1.id = t2.id where t1.id = 10""",
        """SELECT * FROM t1 INNER JOIN t2 ON t1.id = t2.id where t1.id < 10""",
        """SELECT * FROM t1 INNER JOIN t2 ON t1.id = t2.id where t1.id < 1000""",
        """SELECT * FROM t1 INNER JOIN t2 ON t1.id = t2.id""",
    ]
    indexes = [
        (False, False),
        (True, False),
        (True, True),
    ]
    dash_count = 100
    for t1_row_count in t1_sizes:
        for t2_row_count in t2_sizes:
            for table_name, columns in tables.items():
                create_table(table_name, columns)
                row_count = t1_row_count if table_name == "t1" else t2_row_count
                insert_data_into_table(table_name, columns, row_count)
            logging.info("-"*dash_count)
            logging.info(f"TABLE SIZES:\nT1 SIZE: {t1_row_count}, T2 SIZE: {t2_row_count}")
            logging.info("-"*dash_count)
            for index_on_t1, index_on_t2 in indexes:
                add_indexes(index_on_t1, index_on_t2)
                logging.info("-"*dash_count)
                logging.info(f"INDEXES:\nINDEX ON t1(id): {index_on_t1}, INDEX ON t2(id): {index_on_t2}")
                logging.info("-"*dash_count)
                for query in queries:
                    query_plan = get_query_plan(query)
                    logging.info(f"QUERY: {query}")
                    logging.info("-"*dash_count)
                    logging.info(f"QUERYPLAN: \n{query_plan}")
                    logging.info("-"*dash_count)
            logging.info("\n")

if __name__ == "__main__":
    run_tests()
