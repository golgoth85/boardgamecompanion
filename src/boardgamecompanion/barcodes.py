class BarcodeError(ValueError):
    pass


def normalize_barcode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(char for char in str(value).upper() if char.isalnum())
    return normalized or None
