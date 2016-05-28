import sqlite3
import json

"""
Run this file separately. Extracts needed data from fuzzwork's sde sqlite conversion.
"""


def ccp_sde():
    filename = input("Path to SDE File: ").strip('"')

    connection = sqlite3.connect(filename)
    connection.text_factory = lambda x: str(x, 'iso-8859-1')
    cursor = connection.cursor()

    stations = {}
    marketable_items = {}
    skills = {}
    materials = {}

    for row in cursor.execute("SELECT stationID, stationName FROM staStations"):
        stations[int(row[0])] = row[1]

    for row in cursor.execute(
            (
            "SELECT inv.typeID, inv.typeName, inv.volume, meta, img.marketGroupID, dtaRefine.valueInt, inv.portionSize,"
            " InM.baseShipMarketID"
            " FROM invGroups AS ing"
            " LEFT JOIN invTypes AS inv ON ing.groupID = inv.groupID"
            " LEFT JOIN invMarketGroups img ON img.marketGroupID = inv.marketGroupID"
            " LEFT JOIN (SELECT *,"
            " (CASE WHEN InMP3.parentGroupID IS NULL"
            " THEN CASE WHEN InMP2.parentGroupID IS NULL"
            " THEN InMP1.marketGroupID"
            " ELSE InMP2.marketGroupID END"
            " ELSE InMP3.marketGroupID END) AS baseShipMarketID"
            " FROM invGroups"
            " LEFT JOIN invTypes ON invGroups.groupID = invTypes.groupID"
            " LEFT JOIN invMarketGroups AS InM ON invTypes.marketGroupID = InM.marketGroupID"
            " LEFT JOIN invMarketGroups AS InMP1 ON InM.parentGroupID = InMP1.marketGroupID"
            " LEFT JOIN invMarketGroups AS InMP2 ON InMP1.parentGroupID = InMP2.marketGroupID"
            " LEFT JOIN invMarketGroups AS InMP3 ON InMP2.parentGroupID = InMP3.marketGroupID"
            " WHERE invGroups.categoryID = 6) AS InM ON img.marketGroupID = InM.marketGroupID"
            " AND InM.typeName = inv.typeName"
            " LEFT JOIN (select coalesce(valueFloat, valueInt) meta, typeID"
            " from dgmTypeAttributes where attributeID = 633) dtaMeta On dtaMeta.typeID = inv.typeID"
            " LEFT JOIN (select typeID, valueInt, attributeID"
            " from dgmTypeAttributes where attributeID = 790) dtaRefine ON dtaRefine.typeID = inv.typeID"
            " WHERE inv.marketGroupID IS NOT NULL"
            )
    ):
        marketable_items[int(row[0])] = {"name": row[1],
                                         "volume": row[2],
                                         "meta": int(row[3]) if row[3] else None,
                                         "market_group_id": row[4],
                                         "skill_id": row[5],
                                         "batch": row[6],
                                         "ship_group_id": row[7]}

    for row in cursor.execute("SELECT typeID, typeName FROM invTypes WHERE invTypes.groupID IN " +
                              "(SELECT groupID FROM invGroups WHERE invGroups.categoryID = 16)"):
        skills[int(row[0])] = row[1]

    for row in cursor.execute("SELECT typeID, materialTypeID, quantity FROM invTypeMaterials"):
        materials.setdefault(int(row[0]), [])
        materials[int(row[0])].append({"type_id": int(row[1]), "amount": int(row[2])})

    with open("staStations.json", "w") as stations_file:
        json.dump(stations, stations_file, sort_keys=True, indent=4, separators=(',', ': '))
    with open("../static/staStations.json", "w") as static_file:
        json.dump(stations, static_file, sort_keys=True, indent=4, separators=(',', ': '))
    with open("invTypes.json", "w") as types_file:
        json.dump(marketable_items, types_file, sort_keys=True, indent=4, separators=(',', ': '))
    with open("invTypes_skills.json", "w") as skills_file:
        json.dump(skills, skills_file, sort_keys=True, indent=4, separators=(',', ': '))
    with open("invTypeMaterials.json", "w") as materials_file:
        json.dump(materials, materials_file, sort_keys=True, indent=4, separators=(',', ': '))


def fuzzwork_volumes():
    filename = input("Path to SDE File: ")

    connection = sqlite3.connect(filename)
    connection.text_factory = lambda x: str(x, 'iso-8859-1')
    cursor = connection.cursor()

    volumes = {}

    for row in cursor.execute("SELECT typeid, volume FROM invVolumes"):
        volumes[row[0]] = row[1]

    with open("invVolumes.json", "w") as volumes_file:
        json.dump(volumes, volumes_file, sort_keys=True, indent=4, separators=(',', ': '))

if __name__ == "__main__":
    ccp_sde()
