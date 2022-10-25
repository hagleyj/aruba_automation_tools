#!/usr/bin/env python3

from ipaddress import ip_address, ip_network
import requests
from dataclasses import dataclass, field
from constants import *


# This is a class to store the config data from the conductors.  We only store what is needed
@dataclass
class ArubaConfig:
    system_profile: dict = field(default_factory=dict)
    reg_domain_profile: dict = field(default_factory=dict)
    radio_prof_b: dict = field(default_factory=dict)
    radio_prof_a: dict = field(default_factory=dict)
    radio_prof_6: dict = field(default_factory=dict)
    ssid_prof: dict = field(default_factory=dict)
    ap_group: dict = field(default_factory=dict)
    ap_name: dict = field(default_factory=dict)
    virtual_ap: dict = field(default_factory=dict)


# This is a class to store the ap data from the controllers.  This makes it easier to add more data later as we are asked for more data
@dataclass
class ArubaAP:
    name: str
    mac: str = field(default="")
    serial: str = field(default="")
    model: str = field(default="")
    primary: str = field(default="")
    secondary: str = field(default="")
    status: str = field(default="")
    ip: str = field(default="")
    flags: str = field(default="")
    group: str = field(default="")
    bssid: dict = field(default_factory=dict)
    radio: dict = field(default_factory=dict)
    lldp0: dict = field(default_factory=dict)
    lldp1: dict = field(default_factory=dict)


# Class to store the API token per controller or conductor
@dataclass
class ArubaToken:
    wc: str
    uid: str
    csrf: str


# Class to store the inventory of class instantiations for APs and API credentials
@dataclass
class ArubaInventory:
    aps: dict = field(default_factory=dict)
    api: dict = field(default_factory=dict)


# This class does the queries and the work on the controllers.  You need to make sure that ArubaInventory is called and passed into any functions
class ArubaQuery:
    def __init__(self) -> None:
        pass

    def get_aruba_api_token(self, wc, password, inventory):
        r = requests.get(url="https://" + wc + ":4343/v1/api/login?username=" + USERNAME + "&password=" + password, verify=False)
        logindata = r.json()
        # store the api token in a dict to reference later
        tmp_token = ArubaToken(wc, logindata["_global_result"]["UIDARUBA"], logindata["_global_result"]["X-CSRF-Token"])
        inventory.api[wc] = tmp_token

    def aruba_show_command(self, wc, command, inventory):
        # generic show commands api query
        uid = inventory.api[wc].uid
        cookie = dict(SESSION=uid)
        response = requests.get(
            url="https://" + wc + ":4343/v1/configuration/showcommand?command=" + command + "&UIDARUBA=" + uid,
            data="",
            headers={},
            cookies=cookie,
            verify=False,
        )
        return response.json()

    def get_aruba_db(self, wc, networks, inventory, args):
        command = "show+ap+database+long"
        response = self.aruba_show_command(wc, command, inventory)
        # parse json response and update the class
        for ap in response["AP Database"]:
            if ap["Switch IP"] == wc:
                if ap["Status"].startswith("Up"):
                    for network in networks:
                        if args.partial.lower() in ap["Name"].lower() or ip_address(ap["IP Address"]) in ip_network(network) or args.all or args.ap.lower() == ap["Name"].lower():
                            tmp_ap = ArubaAP(
                                name=ap["Name"],
                                mac=ap["Wired MAC Address"],
                                ip=ap["IP Address"],
                                flags=ap["Flags"],
                                model=ap["AP Type"],
                                serial=ap["Serial #"],
                                primary=ap["Switch IP"],
                                secondary=ap["Standby IP"],
                                status=ap["Status"],
                                group=ap["Group"],
                            )
                            inventory.aps[ap["Name"]] = tmp_ap

    def get_aruba_eth1(self, wc, inventory):
        command = "show+ap+lldp+neighbors"
        response = self.aruba_show_command(wc, command, inventory)
        # parse json response and update the class
        for ap in response["AP LLDP Neighbors (Updated every 300 seconds)"]:
            if ap["AP"] in inventory.aps.keys():
                # becase the show lldp is sometimes unreliable we need to see if the ports are up/down
                ap_resp = self.aruba_show_command(wc, "show+ap+port+status+ap-name+" + ap["AP"], inventory)
                for ap_port in ap_resp:
                    for port in ap_resp[ap_port]:
                        if type(port) is dict:
                            if port["Port"] == "0":
                                eth0 = port["Oper"]
                            elif port["Port"] == "1":
                                eth1 = port["Oper"]
                if ap["Interface"] == "eth0":
                    # copy the class, update it, and then put it back
                    tmp = inventory.aps[ap["AP"]]
                    tmp.lldp0 = {ap["Chassis Name/ID"]: ap["Port ID"]}
                    inventory.aps[ap["AP"]] = tmp
                elif eth0 == "up":
                    # copy the class, update it, and then put it back
                    tmp = inventory.aps[ap["AP"]]
                    tmp.lldp0 = {"unknown": "unknown"}
                    inventory.aps[ap["AP"]] = tmp
                if ap["Interface"] == "eth1":
                    # copy the class, update it, and then put it back
                    tmp = inventory.aps[ap["AP"]]
                    tmp.lldp1 = {ap["Chassis Name/ID"]: ap["Port ID"]}
                    inventory.aps[ap["AP"]] = tmp
                elif eth1 == "up":
                    # copy the class, update it, and then put it back
                    tmp = inventory.aps[ap["AP"]]
                    tmp.lldp1 = {"unknown": "unknown"}
                    inventory.aps[ap["AP"]] = tmp

    def get_bssid_table(self, wc, inventory):
        command = "show+ap+bss-table+details"
        response = self.aruba_show_command(wc, command, inventory)
        for ap in response["Aruba AP BSS Table"]:
            if ap["ap name"] in inventory.aps.keys():
                # copy the class, update it, and then put it back
                tmp = inventory.aps[ap["ap name"]]
                bss_dict = {
                    ap["bss"]: {
                        "band": ap["band/ht-mode/bandwidth"],
                        "essid": ap["ess"],
                        "flags": ap["flags"],
                        "clients": ap["active-clients"],
                        "channel": ap["ch/EIRP/max-EIRP"].split("/")[0],
                        "eirp": ap["ch/EIRP/max-EIRP"].split("/")[1],
                        "max-eirp": ap["ch/EIRP/max-EIRP"].split("/")[2],
                    }
                }
                tmp.bssid.update(bss_dict)
                inventory.aps[ap["ap name"]] = tmp

    def get_radio_database(self, wc, inventory):
        command = "show+ap+radio-database"
        response = self.aruba_show_command(wc, command, inventory)
        for ap in response["AP Radio Database"]:
            if ap["Name"] in inventory.aps.keys():
                # copy the class, update it, and then put it back
                tmp = inventory.aps[ap["Name"]]
                for radio in ("Radio 0 Band/Chan/HT-Type/EIRP", "Radio 1 Band/Chan/HT-Type/EIRP", "Radio 2 Band/Chan/HT-Type/EIRP"):
                    if "0" in radio:
                        radio_dict_num = "radio0"
                    elif "1" in radio:
                        radio_dict_num = "radio1"
                    elif "2" in radio:
                        radio_dict_num = "radio2"
                    if ap[radio] == "N/A" or ap[radio].startswith("Disabled"):
                        channel = power = band = "N/A"
                    else:
                        channel = ap[radio].split("/")[0].strip("AP:")
                        power = ap[radio].split("/")[1]
                        band = ap[radio].split("/")[3]
                    radio_dict = {
                        radio_dict_num: {"channel": channel, "power": power, "band": band},
                    }
                    tmp.radio.update(radio_dict)
                inventory.aps[ap["Name"]] = tmp

    def get_aruba_config(self, dn, inventory, config_class):
        # api command to get the config from either AA or Dearborn
        uid = inventory.api[dn].uid
        cookie = dict(SESSION=uid)
        response = requests.get(
            url="https://" + dn + ":4343/v1/configuration/object/config?config_path=" + CONFIG_PATH + "&type=committed&UIDARUBA=" + uid,
            data="",
            headers={},
            cookies=cookie,
            verify=False,
        )
        for item in response.json()["_data"]:
            if item == "reg_domain_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.reg_domain_profile.update(conf_dict)
            elif item == "ap_a_radio_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.radio_prof_a.update(conf_dict)
            elif item == "ap_g_radio_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.radio_prof_b.update(conf_dict)
            elif item == "ap_6ghz_radio_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.radio_prof_6.update(conf_dict)
            elif item == "ssid_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.ssid_prof.update(conf_dict)
            elif item == "ap_group":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.ap_group.update(conf_dict)
            elif item == "ap_name":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.ap_name.update(conf_dict)
            elif item == "ap_sys_prof":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.system_profile.update(conf_dict)
            elif item == "virtual_ap":
                for conf in response.json()["_data"][item]:
                    conf_dict = {conf["profile-name"]: conf}
                    config_class.virtual_ap.update(conf_dict)
        return None
