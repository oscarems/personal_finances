from datetime import date


def _fractional_years(start: date, end: date) -> float:
    """Return the number of years between two dates as a float (day-precise)."""
    return (end - start).days / 365.25


def apply_expected_appreciation(
    value: float,
    expected_rate: float | None,
    as_of_date: date | None,
    reference_date: date | None = None
) -> float:
    if value is None:
        return 0.0

    if not expected_rate or not as_of_date:
        return value

    reference_date = reference_date or date.today()
    if reference_date <= as_of_date:
        return value

    years_elapsed = _fractional_years(as_of_date, reference_date)
    if years_elapsed <= 0:
        return value

    return value * ((1 + (expected_rate / 100)) ** years_elapsed)


def apply_annual_appreciation_on_january(
    value: float,
    expected_rate: float | None,
    as_of_date: date | None,
    reference_date: date | None = None
) -> float:
    if value is None:
        return 0.0

    if not expected_rate or not as_of_date:
        return value

    reference_date = reference_date or date.today()
    if reference_date <= as_of_date:
        return value

    years_elapsed = _fractional_years(as_of_date, reference_date)
    if years_elapsed <= 0:
        return value

    return value * ((1 + (expected_rate / 100)) ** years_elapsed)


def apply_depreciation(
    value: float,
    method: str | None,
    rate: float | None,
    years: int | None,
    salvage_value: float | None,
    start_date: date | None,
    reference_date: date | None = None
) -> float:
    if value is None:
        return 0.0

    if not method or method == "sin_depreciacion" or not start_date:
        return value

    reference_date = reference_date or date.today()
    if reference_date <= start_date:
        return value

    years_elapsed = (reference_date - start_date).days / 365
    if years_elapsed <= 0:
        return value

    salvage_value = salvage_value or 0.0

    if method == "linea_recta":
        if not years or years <= 0:
            return value
        depreciable_value = max(value - salvage_value, 0)
        annual_depreciation = depreciable_value / years
        depreciated_value = value - (annual_depreciation * years_elapsed)
    elif method == "saldo_decreciente":
        if not rate or rate <= 0:
            return value
        depreciated_value = value * ((1 - (rate / 100)) ** years_elapsed)
    elif method == "doble_saldo_decreciente":
        if not years or years <= 0:
            return value
        rate = 2 / years
        depreciated_value = value * ((1 - rate) ** years_elapsed)
    else:
        return value

    return max(depreciated_value, salvage_value)
