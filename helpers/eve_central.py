import json

import requests


def market_hub_prices(id_list):
    """

    :param id_list: [id, ...]
    :return: prices[id] = lowest_sell_price
    """

    usable = True

    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)

    id_list = list(set(id_list))

    payload = {
        "typeid": id_list,
        "usesystem": int(base_config["market_hub_system"])
    }
    if id_list:
        ec_response = requests.get("http://api.eve-central.com/api/marketstat/json", data=payload)
        try:
            ec_prices = ec_response.json()
        except ValueError:
            usable = False
            print(ec_response.text)
            ec_prices = {}
    else:
        ec_prices = {}

    prices = {}

    if ec_prices:
        for item in ec_prices:
            prices[item["sell"]["forQuery"]["types"][0]] = {"sell": float(item["sell"]["min"]),
                                                            "buy": float(item["buy"]["max"])}
    else:
        # noinspection PyTypeChecker
        for item in id_list:
            prices[item] = {"sell": 0, "buy": 0}

    return prices, usable
