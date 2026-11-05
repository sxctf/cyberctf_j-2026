from langchain.tools import tool


@tool("convert_temperature", description="Convert temperature between C, F, and K")
def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert temperature from one unit to another."""
    units = {"C": "Celsius", "F": "Fahrenheit", "K": "Kelvin"}

    if from_unit not in units or to_unit not in units:
        raise ValueError(f"Invalid units. Use: {', '.join(units.keys())}")

    # Convert to Celsius first
    if from_unit == "C":
        celsius = value
    elif from_unit == "F":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "K":
        celsius = value - 273.15

    # Convert from Celsius to target
    if to_unit == "C":
        return round(celsius, 2)
    elif to_unit == "F":
        return round(celsius * 9 / 5 + 32, 2)
    elif to_unit == "K":
        return round(celsius + 273.15, 2)
