import pytest
from fastapi import HTTPException
from dbmanager import sqlbuild


def test_validate_identifier_accepts_normal_name():
    sqlbuild.validate_identifier("my_table", "table name")  # no raise


def test_validate_identifier_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        sqlbuild.validate_identifier("  ", "table name")
    assert exc.value.status_code == 400


def test_validate_identifier_rejects_overlong():
    with pytest.raises(HTTPException):
        sqlbuild.validate_identifier("x" * 64, "table name")


def test_validate_type_accepts_known_forms():
    for t in ["integer", "varchar(255)", "numeric(10, 2)", "text[]",
              "timestamp with time zone"]:
        sqlbuild.validate_type(t)  # no raise


def test_validate_type_rejects_injection():
    with pytest.raises(HTTPException):
        sqlbuild.validate_type("integer); DROP TABLE x; --")


def test_create_database_sql():
    rendered = sqlbuild.create_database("shop", owner=None, encoding=None).as_string()
    assert rendered == 'CREATE DATABASE "shop"'


def test_drop_database_force_sql():
    rendered = sqlbuild.drop_database("shop", force=True).as_string()
    assert rendered == 'DROP DATABASE "shop" WITH (FORCE)'
