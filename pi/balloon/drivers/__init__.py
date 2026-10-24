"""Minimal I2C drivers for the Grove sensors we might have. Each driver exposes
`read()` -> dict of fields, a class attribute `FIELDS` (list of field names) and
`KIND` (what it measures). Written against smbus2 so no vendor library is needed."""
