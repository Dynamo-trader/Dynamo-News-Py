import logging
import numbers
from datetime import datetime
from typing import Union

import numpy as np
from PIL import Image
from matplotlib import pyplot as plt

from dynamo_news.models import ForexFactory


def get_plot(
    plot_data: list[list[Union[datetime, int]]], condition: ForexFactory
) -> str:
    """
    plot_data: [
        [
            datetime,  # date
            6.2,   # actual
            null,  # forecast
            6.1  # previous
        ]
    ]
    """
    plot_data.reverse()

    if condition.label != "NFP":
        plot_data_limited = plot_data[:60]
    else:
        plot_data_limited = plot_data[:51]

    plot_data = []
    monthly_actual = []
    year_positions = []
    years = []
    last_y = 0
    max_years = 5  # assumed every year has 12 entries
    c = 0

    for md in plot_data_limited:
        year = md[0].year
        if year not in years and len(years) != max_years:
            years.append(year)

    years.reverse()
    for md in plot_data_limited:
        x = md[0].year
        if x in years:
            plot_data.append(md)

            if last_y == 0:
                last_y = x
                year_positions.append(c)
                c += 1
            elif last_y == x:
                c += 1
            else:
                year_positions.append(c)
                last_y = x
                c += 1

    for x in plot_data:
        actual = x[1]
        if not isinstance(x[1], numbers.Number):
            continue
        monthly_actual.append(actual)

    # Create a continuous numerical x-axis
    x = np.arange(len(monthly_actual))
    monthly_actual.reverse()
    plt.bar(
        x, monthly_actual, tick_label=[""] * len(monthly_actual)
    )  # Remove x-axis labels
    # Annotate the years at the desired positions
    plt.xticks(year_positions, years)  # NOQA

    plt.xlabel("Year")
    sign = "%" if condition.label != "NFP" else "K"
    plt.ylabel(f"{condition.label} {sign}")
    plt.title(f"{condition.currency} {condition.title}")
    plt.grid(axis="y", linestyle="--", alpha=0.7)

    file_name = "plot_file.png"
    plt.savefig(file_name)
    plt.close()

    try:
        img = Image.open(file_name)
        logo = Image.open("./images/dynamo_logo_flat.jpg")
        logo = logo.resize((155, 23))
        img.paste(logo, (round(img.width - 180), 5))
        img.save(file_name)
    except Exception as e:
        logging.error(e)
    return file_name
