#!/usr/bin/env python3

from ipaddress import ip_address, ip_network
import requests
from dataclasses import dataclass, field
from constants import *
from utils import utils
import time
import json

# from netmiko import ConnectHandler


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
                            inventory.aps[ap["Name"]] = ArubaAP(
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
                            # inventory.aps[ap["Name"]] = tmp_ap

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
                    # tmp = inventory.aps[ap["AP"]]
                    inventory.aps[ap["AP"]].lldp0.update({ap["Chassis Name/ID"]: ap["Port ID"]})
                    # inventory.aps[ap["AP"]] = tmp
                elif eth0 == "up":
                    # copy the class, update it, and then put it back
                    # tmp = inventory.aps[ap["AP"]]
                    inventory.aps[ap["AP"]].lldp0.update({"unknown": "unknown"})
                    # inventory.aps[ap["AP"]] = tmp
                if ap["Interface"] == "eth1":
                    # copy the class, update it, and then put it back
                    # tmp = inventory.aps[ap["AP"]]
                    inventory.aps[ap["AP"]].lldp1.update({ap["Chassis Name/ID"]: ap["Port ID"]})
                    # inventory.aps[ap["AP"]] = tmp
                elif eth1 == "up":
                    # copy the class, update it, and then put it back
                    # tmp = inventory.aps[ap["AP"]]
                    inventory.aps[ap["AP"]].lldp1.update({"unknown": "unknown"})
                    # inventory.aps[ap["AP"]] = tmp

    def get_bssid_table(self, wc, inventory):
        command = "show+ap+bss-table+details"
        response = self.aruba_show_command(wc, command, inventory)
        for ap in response["Aruba AP BSS Table"]:
            if ap["ap name"] in inventory.aps.keys():
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
                inventory.aps[ap["ap name"]].bssid.update(bss_dict)

    def get_radio_database(self, wc, inventory):
        command = "show+ap+radio-database"
        response = self.aruba_show_command(wc, command, inventory)
        for ap in response["AP Radio Database"]:
            if ap["Name"] in inventory.aps.keys():
                # copy the class, update it, and then put it back
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
                inventory.aps[ap["Name"]].radio.update(radio_dict)

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

    def ap_status(self, wc, args, inventory, query):
        command = "show+ap+details+ap-name+" + args.ap
        response = self.aruba_show_command(wc, command, inventory)
        for item in response["AP " + args.ap + " Basic Information"]:
            if item["Item"] == "Status":
                status = item["Value"]
            elif item["Item"] == "Up time":
                uptime = item["Value"]

        command = "show+ap+lldp+neighbors+ap-name+" + args.ap
        response = query.aruba_show_command(wc, command, inventory)
        neighbor = response["AP LLDP Neighbors (Updated every 300 seconds)"][0]["Chassis Name/ID"]
        interface = response["AP LLDP Neighbors (Updated every 300 seconds)"][0]["Interface"]
        neighbor_port = response["AP LLDP Neighbors (Updated every 300 seconds)"][0]["Port ID"]

        if status == "Up":
            return "```AP {} has been up for {}, connected on {} to {} port {}```".format(args.ap, uptime, interface, neighbor, neighbor_port)
        else:
            return "```AP {} is {}```".format(args.ap, status)

    def aruba_denylist_query(self, wc, args, inventory, query):
        command = "show ap denylist-clients"
        response = self.aruba_show_command(wc, command, inventory)
        mac = utils.mac_to_colon_separated(args.mac).lower()
        for client in response["Client Denylist"]:
            if mac == client["STA"]:
                reason = client["reason"]
                time = client["block-time(sec)"]
                remaining = ["remaining time(sec)"]
                print("{} was block for {}, time remaining {} on {}".format(mac, reason, remaining, wc))
                return "{} was block for {}, time remaining {} on {}".format(mac, reason, remaining, wc)
        print("{} is not currently on the denylist on {}".format(mac, wc))
        return "```{} is not currently on the denylist on {}```".format(mac, wc)

    def aruba_wifi_client(self, wc, args, inventory, query):
        mac_search = user_search = "NONE"

        command = "show+global-user-table+list"
        response = self.aruba_show_command(wc, command, inventory)

        if args.mac != "NONE":
            mac_search = utils.mac_to_colon_separated(args.mac).lower()

        if args.user != "NONE":
            user_search = args.user.lower()

        return_message = ""
        for user in response["Global Users"]:
            if str(user["MAC"]) == mac_search or user_search in str(user["Name"]):
                print("{},{},{},{},{},{},{},{},{}".format(user["MAC"], user["Name"], user["IP"], user["Essid"], user["Bssid"], user["AP name"], user["Phy"], user["Role"], user["Current switch"]))
                return_message = (
                    return_message
                    + "\n"
                    + "{},{},{},{},{},{},{},{},{}".format(user["MAC"], user["Name"], user["IP"], user["Essid"], user["Bssid"], user["AP name"], user["Phy"], user["Role"], user["Current switch"])
                )
        return return_message


class ArubaPost:
    def __init__(self) -> None:
        self.query = ArubaQuery()

    def rename_ap(self, wc, inventory, query, args, ap_config):
        command = "show+ap+database+long"
        response = self.query.aruba_show_command(wc, command, inventory)
        # parse json response and update the class
        for ap in response["AP Database"]:
            if ap["Status"].startswith("Up"):
                tmp_ap = ArubaAP(ap["Name"])
                tmp_ap.mac = ap["Wired MAC Address"]
                tmp_ap.group = ap["Group"]
                inventory.aps[ap["Wired MAC Address"]] = tmp_ap

        uid = inventory.api[wc].uid
        cookie = dict(SESSION=uid)

        for ap in ap_config:
            if ap in inventory.aps.keys():
                if args.force:
                    rename_data = {"wired-mac": inventory.aps[ap].mac, "new-name": ap_config[ap]["name"]}
                    rename_ap = requests.post(
                        url="https://" + wc + ":4343/v1/configuration/object/ap_rename?config_path=%2Fmm&UIDARUBA=" + uid,
                        data=json.dumps(rename_data),
                        headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                        cookies=cookie,
                        verify=False,
                    )
                    if rename_ap.ok:
                        print("Renamed " + inventory.aps[ap].name + " to " + ap_config[ap]["name"])
                    else:
                        print("API Failure")

                    group_data = {"wired-mac": inventory.aps[ap].mac, "new-group": ap_config[ap]["group"]}
                    regroup_ap = requests.post(
                        url="https://" + wc + ":4343/v1/configuration/object/ap_regroup?config_path=%2Fmm&UIDARUBA=" + uid,
                        data=json.dumps(group_data),
                        headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                        cookies=cookie,
                        verify=False,
                    )
                    if regroup_ap.ok:
                        print("Changed " + inventory.aps[ap].name + " to group " + ap_config[ap]["group"])
                    else:
                        print("API Failure")
                else:
                    if ap != "NONE":
                        # if new name doesn't match existing name, then change it
                        if inventory.aps[ap].name != ap_config[ap]["name"]:
                            rename_data = {"wired-mac": inventory.aps[ap].mac, "new-name": ap_config[ap]["name"]}
                            rename_ap = requests.post(
                                url="https://" + wc + ":4343/v1/configuration/object/ap_rename?config_path=%2Fmm&UIDARUBA=" + uid,
                                data=json.dumps(rename_data),
                                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                                cookies=cookie,
                                verify=False,
                            )
                            if rename_ap.ok:
                                print("Renamed " + inventory.aps[ap].name + " to " + ap_config[ap]["name"])
                            else:
                                print("API Failure")
                        if inventory.aps[ap].group != ap_config[ap]["group"]:
                            group_data = {"wired-mac": inventory.aps[ap].mac, "new-group": ap_config[ap]["group"]}
                            regroup_ap = requests.post(
                                url="https://" + wc + ":4343/v1/configuration/object/ap_regroup?config_path=%2Fmm&UIDARUBA=" + uid,
                                data=json.dumps(group_data),
                                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                                cookies=cookie,
                                verify=False,
                            )
                            if regroup_ap.ok:
                                print("Changed " + inventory.aps[ap].name + " to group " + ap_config[ap]["group"])
                            else:
                                print("API Failure")

    def reboot_ap(self, wc, inventory, query, args):
        command = "show+ap+database+long"
        response = self.query.aruba_show_command(wc, command, inventory)
        # parse json response and update the class
        if args.name:
            ap_to_reboot = args.name
            for ap in response["AP Database"]:
                if ap["Status"].startswith("Up") and ap["Switch IP"] == wc:
                    tmp_ap = ArubaAP(ap["Name"])
                    tmp_ap.mac = ap["Wired MAC Address"]
                    tmp_ap.group = ap["Group"]
                    inventory.aps[ap["Name"]] = tmp_ap
        elif args.mac:
            ap_to_reboot = utils.mac_to_colon_separated(args.mac).lower()
            for ap in response["AP Database"]:
                if ap["Status"].startswith("Up") and ap["Switch IP"] == wc:
                    tmp_ap = ArubaAP(ap["Name"])
                    tmp_ap.mac = ap["Wired MAC Address"]
                    tmp_ap.group = ap["Group"]
                    inventory.aps[ap["Wired MAC Address"]] = tmp_ap

        uid = inventory.api[wc].uid
        cookie = dict(SESSION=uid)

        if ap_to_reboot in inventory.aps.keys():
            reboot_data = {"wired-mac": inventory.aps[ap_to_reboot].mac}
            reboot_ap = requests.post(
                url="https://" + wc + ":4343/v1/configuration/object/apboot?config_path=%2Fmm&UIDARUBA=" + uid,
                data=json.dumps(reboot_data),
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                cookies=cookie,
                verify=False,
            )
            if reboot_ap.ok:
                print("Rebooted " + ap_to_reboot)
                return "Rebooted " + ap_to_reboot
            else:
                print("API Failure")

    def denylist_add_remove(self, wc, args, inventory, query):
        mac_search = utils.mac_to_colon_separated(args.mac).lower()
        if args.remove:
            uid = inventory.api[wc].uid
            cookie = dict(SESSION=uid)
            user_del = requests.post(
                url="https://" + wc + ":4343/v1/configuration/object/aaa_user_delete?config_path=%2Fmm&UIDARUBA=" + uid,
                data=json.dumps({"macaddr": mac_search}),
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                cookies=cookie,
                verify=False,
            )
            if user_del.ok:
                print("Mac {} removed from {}".format(mac_search, wc))
                return "Mac {} removed from {}".format(mac_search, wc)

        if args.dl_add:
            uid = inventory.api[wc].uid
            cookie = dict(SESSION=uid)
            user_del = requests.post(
                url="https://" + wc + ":4343/v1/configuration/object/stm_blacklist_client_add?config_path=%2Fmm&UIDARUBA=" + uid,
                data=json.dumps({"client-mac": mac_search}),
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                cookies=cookie,
                verify=False,
            )
            if user_del.ok:
                print("Mac {} added to denylist on {}".format(mac_search, wc))
                return "Mac {} added to denylist on {}".format(mac_search, wc)

        if args.dl_remove:
            uid = inventory.api[wc].uid
            cookie = dict(SESSION=uid)
            user_del = requests.post(
                url="https://" + wc + ":4343/v1/configuration/object/stm_blacklist_client_remove?config_path=%2Fmm&UIDARUBA=" + uid,
                data=json.dumps({"client-mac": mac_search}),
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                cookies=cookie,
                verify=False,
            )
            if user_del.ok:
                print("Mac {} removed from denylist on {}".format(mac_search, wc))
                return "Mac {} removed from denylist on {}".format(mac_search, wc)

    def blink_ap(self, wc, inventory, args, query):
        command = "show+ap+database+long"
        response = self.query.aruba_show_command(wc, command, inventory)
        # parse json response and update the class
        if args.name:
            ap_to_blink = args.name
            for ap in response["AP Database"]:
                if ap["Status"].startswith("Up") and ap["Switch IP"] == wc:
                    tmp_ap = ArubaAP(ap["Name"])
                    tmp_ap.mac(ap["Wired MAC Address"])
                    tmp_ap.group(ap["Group"])
                    inventory.aps[ap["Name"]] = tmp_ap
        elif args.mac:
            ap_to_blink = utils.mac_to_colon_separated(args.mac).lower()
            for ap in response["AP Database"]:
                if ap["Status"].startswith("Up") and ap["Switch IP"] == wc:
                    tmp_ap = ArubaAP(ap["Name"])
                    tmp_ap.mac(ap["Wired MAC Address"])
                    tmp_ap.group(ap["Group"])
                    inventory.aps[ap["Wired MAC Address"]] = tmp_ap

        uid = inventory.api[wc].uid
        cookie = dict(SESSION=uid)

        if ap_to_blink in inventory.aps.keys():
            if args.blink_on:
                blink_data = {"wired-mac": inventory.aps[ap_to_blink].mac, "action_option": "blink"}
                msg = "Blinking LEDs on " + ap_to_blink
            elif args.blink_off:
                blink_data = {"wired-mac": inventory.aps[ap_to_blink].mac, "action_option": "normal"}
                msg = "LEDs normal on " + ap_to_blink
            blink_ap = requests.post(
                url="https://" + wc + ":4343/v1/configuration/object/ap_leds?config_path=%2Fmm&UIDARUBA=" + uid,
                data=json.dumps(blink_data),
                headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                cookies=cookie,
                verify=False,
            )
            if blink_ap.ok:
                print(msg)
                return msg
            else:
                print("API Failure")

    def set_ap_config(self, wc, inventory, args, query, config_class):

        self.query.get_aruba_config(wc, inventory, config_class)

        uid = inventory.api[wc].uid
        cookie = dict(SESSION=uid)

        # these commands are work on specific APs
        if args.ap != "NONE":
            if args.ap_current:
                if args.ap in config_class.args.ap.keys():
                    print("Unique SSIDs on " + args.ap + ":")
                    for ssid in config_class.args.ap[args.ap]["virtual_ap"]:
                        print("  " + ssid["profile-name"])
                else:
                    print(args.ap + " does not have any unique SSIDs configured")

            if args.ap_ssid_add != "NONE":
                ssid_add_list = args.ap_ssid_add.split(",")
                for ssid_vap in ssid_add_list:
                    if ssid_vap in config_class.virtual_ap.keys():
                        ap_ssid_add_data = {"profile-name": args.ap, "virtual_ap": [{"profile-name": ssid_vap}]}
                        ap_ssid_add = requests.post(
                            url="https://" + wc + ":4343/v1/configuration/object/ap_name?config_path=" + CONFIG_PATH + "&UIDARUBA=" + uid,
                            data=json.dumps(ap_ssid_add_data),
                            headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                            cookies=cookie,
                            verify=False,
                        )
                        if ap_ssid_add.ok:
                            print("{} add to {} on {}".format(ssid_vap, args.ap, wc))
                        else:
                            print("API Failure")
                    else:
                        print(ssid_vap + " is not a valid VAP")

            if args.ap_ssid_remove != "NONE":
                ssid_remove_list = args.ap_ssid_remove.split(",")
                for ssid_vap in ssid_remove_list:
                    if ssid_vap in config_class.virtual_ap.keys():
                        ap_ssid_remove_data = {"profile-name": args.ap, "virtual_ap": [{"profile-name": ssid_vap}], "_action": "delete"}
                        ap_ssid_remove = requests.post(
                            url="https://" + wc + ":4343/v1/configuration/object/ap_name?config_path=" + CONFIG_PATH + "&UIDARUBA=" + uid,
                            data=json.dumps(ap_ssid_remove_data),
                            headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                            cookies=cookie,
                            verify=False,
                        )
                        if ap_ssid_remove.ok:
                            print("{} removed from {} on {}".format(ssid_vap, args.ap, wc))
                        else:
                            print("API Failure")
                    else:
                        print(ssid_vap + " is not a valid VAP")

        # these commands are work on specific groups
        if args.ssid != "NONE":
            if args.ssid in config_class.ssid_prof.keys():
                if args.ssid_current:
                    print(args.ssid + ":")
                    if "essid" in config_class.ssid_prof[args.ssid].keys():
                        print("  ESSID: " + config_class.ssid_prof[args.ssid]["essid"]["essid"])
                    if "wpa_passphrase" in config_class.ssid_prof[args.ssid].keys():
                        print("  PSK: " + config_class.ssid_prof[args.ssid]["wpa_passphrase"]["wpa-passphrase"])

                if args.ssid_essid != "NONE":
                    essid_data = {"profile-name": args.ssid, "essid": {"essid": args.ssid_essid}}
                    update_essid = requests.post(
                        url="https://" + wc + ":4343/v1/configuration/object/ssid_prof?config_path=" + CONFIG_PATH + "&UIDARUBA=" + uid,
                        data=json.dumps(essid_data),
                        headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                        cookies=cookie,
                        verify=False,
                    )
                    if update_essid.ok:
                        print("Updated ESSID on {} on {}".format(args.ssid, wc))
                    else:
                        print("API Failure")

                if args.ssid_psk != "NONE":
                    if "wpa_passphrase" in config_class.ssid_prof[args.ssid].keys():
                        psk_data = {
                            "profile-name": args.ssid,
                            "wpa_passphrase": {"wpa-passphrase": args.ssid_psk},
                        }
                        update_psk = requests.post(
                            url="https://" + wc + ":4343/v1/configuration/object/ssid_prof?config_path=" + CONFIG_PATH + "&UIDARUBA=" + uid,
                            data=json.dumps(psk_data),
                            headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
                            cookies=cookie,
                            verify=False,
                        )
                        if update_psk.ok:
                            print("Updated PSK on {} on {}".format(args.ssid, wc))
                        else:
                            print("API Failure")

            else:
                print("Invalid SSID Profile")

        write_memory = ap_ssid_add = requests.post(
            url="https://" + wc + ":4343/v1/configuration/object/write_memory?config_path=" + CONFIG_PATH + "&UIDARUBA=" + uid,
            data={},
            headers={"Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": inventory.api[wc].csrf},
            cookies=cookie,
            verify=False,
        )

        if args.ssid_list:
            print("SSIDs")
            for vap in config_class.virtual_ap:
                print("- VAP: " + vap)
                print("  - Profile: " + config_class.virtual_ap[vap]["ssid_prof"]["profile-name"])
                print("    - essid: " + config_class.ssid_prof[config_class.virtual_ap[vap]["ssid_prof"]["profile-name"]]["essid"]["essid"])

        return None

    def aruba_set_raw_config(self, mc, password, raw_config):
        conn = {
            "device_type": "aruba_os_ssh",
            "host": mc,
            "username": "umnet",
            "password": password,
            "banner_timeout": 10,
        }

        cd_command = "cd " + CONFIG_PATH

        ch = ConnectHandler(**conn)
        ch.send_command_timing(cd_command, strip_command=False, strip_prompt=False)
        ch.send_config_set(raw_config, delay_factor=5, cmd_verify=False)
        time.sleep(3)
        ch.send_command_timing("write memory", strip_command=False, strip_prompt=False)

        print("Config was pushed to " + mc)
