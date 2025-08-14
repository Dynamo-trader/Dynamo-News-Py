def calculate_pip_value(
    price: float, pip_steps: list[int], decimal_places: int
) -> list[float]:
    """
    Calculate the pip value for a given price and number of pips.

    Parameters:
        price (float): The current price of the currency pair.
        pip_steps (list[int]): The number of pips to adjust.
        decimal_places (int): The number of decimal places for the currency pair.
    Returns:
        list[float]: The value of a pip movement for the given price.
    """

    pip_value: float = 10 ** -(decimal_places - 1)

    return [
        round(
            price + (pip * pip_value) if pip >= 0 else price - (abs(pip) * pip_value),
            decimal_places,
        )
        for pip in pip_steps
    ]
