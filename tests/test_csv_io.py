import pytest

from vrp_demo.csv_io import CSVValidationError, customers_from_csv_text

VALID = """customer_id,x_km,y_km,demand,service_minutes,window_start,window_end
C001,2.5,7.0,4,10,60,180
"""


def test_valid_csv():
    customers = customers_from_csv_text(VALID)
    assert customers[0].customer_id == "C001"
    assert customers[0].demand == 4


def test_rejects_wrong_columns():
    with pytest.raises(CSVValidationError, match="required schema"):
        customers_from_csv_text("customer_id,demand\nC1,2\n")


def test_rejects_bad_window_with_row_number():
    invalid = VALID.replace("60,180", "180,60")
    with pytest.raises(CSVValidationError, match="row 2"):
        customers_from_csv_text(invalid)


def test_rejects_duplicate_ids():
    duplicate = VALID + "C001,1,1,2,5,0,100\n"
    with pytest.raises(CSVValidationError, match="duplicate customer_id"):
        customers_from_csv_text(duplicate)
