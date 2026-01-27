from datetime import date


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

    years_elapsed = (reference_date - as_of_date).days // 365
    if years_elapsed <= 0:
        return value

    return value * ((1 + (expected_rate / 100)) ** years_elapsed)
