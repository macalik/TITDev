import json

import requests


def market_hub_sell_prices(id_list):
    with open("configs/base.json") as base_config_file:
        base_config = json.load(base_config_file)

    payload = {
        "typeid": id_list,
        "regionlimit": int(base_config["market_hub_region"])
    }
    ec_response = requests.get("http://api.eve-central.com/api/marketstat/json", data=payload)
    ec_prices = ec_response.json()

    prices = {}

    for item in ec_prices:
        prices[item["sell"]["forQuery"]["types"][0]] = float(item["sell"]["min"])

    return prices
