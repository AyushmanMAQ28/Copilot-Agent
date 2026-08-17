import pytest
from app.services.csv_loader import CSVValidationError, load_csv


def test_loads_utf8_bom_and_normalizes_values():
    result = load_csv(b"\xef\xbb\xbfname,value\n Ada , 42 \n", "data.csv", 1000, 10)
    assert result.headers == ["name", "value"]
    assert result.rows == [{"name": "Ada", "value": "42"}]


@pytest.mark.parametrize("filename,content,error", [
    ("data.txt", b"name\nAda\n", "Only .csv"),
    ("data.csv", b"name,name\nAda,Grace\n", "unique"),
    ("data.csv", b"name,value\nAda,1,extra\n", "more fields"),
])
def test_rejects_invalid_csv(filename, content, error):
    with pytest.raises(CSVValidationError, match=error):
        load_csv(content, filename, 1000, 10)


def test_rejects_excessive_rows():
    with pytest.raises(CSVValidationError, match="row limit"):
        load_csv(b"name\nAda\nGrace\n", "data.csv", 1000, 1)
