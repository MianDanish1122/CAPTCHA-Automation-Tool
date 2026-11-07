import io
import pytest
from app.services.csv_importer import import_websites


def test_import_valid_csv():
    csv_data = b"company_name,website_url\nAcme Inc,https://acme.org\nBeta LLC,http://beta.io\n"
    res = import_websites(csv_data)
    assert res["success"] is True
    assert res["total_websites"] == 2
    assert res["invalid_rows"] == 0
    assert len(res["websites"]) == 2
    assert res["websites"][0]["company_name"] == "Acme Inc"
    assert res["websites"][0]["website_url"] == "https://acme.org"


def test_import_header_aliases():
    csv_data = b"company,url\nGlobex,https://globex.com\n"
    res = import_websites(csv_data)
    assert res["success"] is True
    assert res["total_websites"] == 1
    assert res["websites"][0]["company_name"] == "Globex"


def test_import_missing_required_headers():
    csv_data = b"wrong_col1,wrong_col2\nVal1,Val2\n"
    res = import_websites(csv_data)
    assert res["success"] is False
    assert "Missing required columns" in res["message"]


def test_import_invalid_rows():
    csv_data = (
        b"company_name,website_url\n"
        b"Valid Co,https://valid.com\n"
        b"No URL Co,\n"
        b",https://nocompany.com\n"
        b"Bad Scheme,ftp://ftp.bad.com\n"
        b"Creds Co,https://user:pass@secret.com\n"
    )
    res = import_websites(csv_data)
    assert res["success"] is True
    assert res["total_websites"] == 1
    assert res["invalid_rows"] == 4
    assert len(res["errors"]) == 4


def test_import_empty_file():
    res = import_websites(b"")
    assert res["success"] is False
    assert "empty" in res["message"].lower()
