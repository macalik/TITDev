import json

import requests


def market_hub_prices(id_list):
    """

    :param id_list: [id, ...]
    :return: prices[id] = lowest_sell_price
    """
    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)

    payload = {
        "typeid": id_list,
        "usesystem": int(base_config["market_hub_system"])
    }
    ec_response = requests.get("http://api.eve-central.com/api/marketstat/json", data=payload)
    ec_prices = ec_response.json()

    prices = {}

    for item in ec_prices:
        prices[item["sell"]["forQuery"]["types"][0]] = {"sell": float(item["sell"]["min"]),
                                                        "buy": float(item["buy"]["max"])}

    return prices
