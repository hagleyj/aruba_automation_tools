#!/usr/bin/env python3

from ipaddress import ip_address, ip_network
from pickletools import read_unicodestring1
import requests
from constants import *



# This is a class to store the config data from the conductors.  We only store what is needed
class ArubaConfig:
    def __init__(self):
        self.system_profile = {}
        self.reg_domain_profile = {}
        self.radio_prof_b = {}
        self.radio_prof_a = {}
        self.radio_prof_6 = {}
        self.ssid_prof = {}
        self.ap_group = {}
        self.ap_name = {}
        self.virtual_ap = {}

    def updateSysProf(self, system_profile):
        self.system_profile.update(system_profile)

    def updateRegDomainProf(self, reg_domain_profile):
        self.reg_domain_profile.update(reg_domain_profile)

    def updateRadioBProf(self, radio_prof_b):
        self.radio_prof_b.update(radio_prof_b)

    def updateRadioAProf(self, radio_prof_a):
        self.radio_prof_a.update(radio_prof_a)

    def updateRadio6Prof(self, radio_prof_6):
        self.radio_prof_6.update(radio_prof_6)

    def updateSSIDProf(self, ssid_prof):
        self.ssid_prof.update(ssid_prof)

    def updateApGroup(self, ap_group):
        self.ap_group.update(ap_group)

    def updateAPName(self, ap_name):
        self.ap_name.update(ap_name)

    def updateVirtualAP(self, virtual_ap):
        self.virtual_ap.update(virtual_ap)


# This is a class to store the ap data from the controllers.  This makes it easier to add more data later as we are asked for more data
class ArubaAP:
    def __init__(self, name):
        # Key off of AP name
        self.name = name

        # Default the variables
        self.mac = None
        self.serial = None
        self.model = None
        self.primary = None
        self.secondary = None
        self.status = None
        self.ip = None
        self.flags = None
        self.group = None
        self.bssid = {}
        self.radio = {}
        self.lldp0 = {}
        self.lldp1 = {}

    # Set values
    def setMac(self, mac):
        self.mac = mac

    def setSerial(self, serial):
        self.serial = serial

    def setModel(self, model):
        self.model = model

    def setPrimary(self, primary):
        self.primary = primary

    def setSecondary(self, secondary):
        self.secondary = secondary

    def setStatus(self, status):
        self.status = status

    def setIP(self, ip):
        self.ip = ip

    def setFlags(self, flags):
        self.flags = flags

    def setGroup(self, group):
        self.group = group

    def setBSSID(self, bssid):
        self.bssid.update(bssid)

    def setRadio(self, radio):
        self.radio.update(radio)

    def setLLDP0(self, neighbor, port):
        self.lldp0 = {neighbor: port}

    def setLLDP1(self, neighbor, port):
        self.lldp1 = {neighbor: port}


class ArubaToken:
    def __init__(self, wc, uid, csrf):
        self.wc = wc
        self.uid = uid
        self.csrf = csrf


def get_aruba_api_token(wc, password, wc_api):
    r = requests.get(url="https://" + wc + ":4343/v1/api/login?username=umnet&password=" + password, verify=False)
    logindata = r.json()
    # store the api token in a dict to reference later
    tmp_token = ArubaToken(wc, logindata["_global_result"]["UIDARUBA"], logindata["_global_result"]["X-CSRF-Token"])
    wc_api.setdefault(wc, tmp_token)
    # wc_api[wc] = logindata["_global_result"]["UIDARUBA"]


def get_aruba_db(wc, networks, wc_api, args, ap_list):
    command = "show+ap+database+long"
    response = aruba_show_command(wc, command, wc_api)
    # parse json response and update the class
    for ap in response["AP Database"]:
        if ap["Switch IP"] == wc:
            if ap["Status"].startswith("Up"):
                for network in networks:
                    if args.partial.lower() in ap["Name"].lower() or ip_address(ap["IP Address"]) in ip_network(network) or args.all or args.ap.lower() == ap["Name"].lower():
                        tmp_ap = ArubaAP(ap["Name"])
                        tmp_ap.setMac(ap["Wired MAC Address"])
                        tmp_ap.setIP(ap["IP Address"])
                        tmp_ap.setFlags(ap["Flags"])
                        tmp_ap.setModel(ap["AP Type"])
                        tmp_ap.setSerial(ap["Serial #"])
                        tmp_ap.setPrimary(ap["Switch IP"])
                        tmp_ap.setSecondary(ap["Standby IP"])
                        tmp_ap.setStatus(ap["Status"])
                        tmp_ap.setGroup(ap["Group"])
                        ap_list.setdefault(ap["Name"], tmp_ap)
    return ap_list


def get_aruba_eth1(wc, wc_api, ap_list):
    command = "show+ap+lldp+neighbors"
    response = aruba_show_command(wc, command, wc_api)
    # parse json response and update the class
    for ap in response["AP LLDP Neighbors (Updated every 300 seconds)"]:
        if ap["AP"] in ap_list.keys():
            # becase the show lldp is sometimes unreliable we need to see if the ports are up/down
            ap_resp = aruba_show_command(wc, "show+ap+port+status+ap-name+" + ap["AP"], wc_api)
            for ap_port in ap_resp:
                for port in ap_resp[ap_port]:
                    if type(port) is dict:
                        if port["Port"] == "0":
                            eth0 = port["Oper"]
                        elif port["Port"] == "1":
                            eth1 = port["Oper"]
            if ap["Interface"] == "eth0":
                # copy the class, update it, and then put it back
                tmp = ap_list[ap["AP"]]
                tmp.setLLDP0(ap["Chassis Name/ID"], ap["Port ID"])
                ap_list[ap["AP"]] = tmp
            elif eth0 == "up":
                # copy the class, update it, and then put it back
                tmp = ap_list[ap["AP"]]
                tmp.setLLDP0("unknown", "unknown")
                ap_list[ap["AP"]] = tmp
            if ap["Interface"] == "eth1":
                # copy the class, update it, and then put it back
                tmp = ap_list[ap["AP"]]
                tmp.setLLDP1(ap["Chassis Name/ID"], ap["Port ID"])
                ap_list[ap["AP"]] = tmp
            elif eth1 == "up":
                # copy the class, update it, and then put it back
                tmp = ap_list[ap["AP"]]
                tmp.setLLDP1("unknown", "unknown")
                ap_list[ap["AP"]] = tmp
    return ap_list


def get_bssid_table(wc, wc_api, ap_list):
    command = "show+ap+bss-table+details"
    response = aruba_show_command(wc, command, wc_api)
    for ap in response["Aruba AP BSS Table"]:
        if ap["ap name"] in ap_list.keys():
            # copy the class, update it, and then put it back
            tmp = ap_list[ap["ap name"]]
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
            tmp.setBSSID(bss_dict)
            ap_list[ap["ap name"]] = tmp
    return ap_list


def get_radio_database(wc, wc_api, ap_list):
    command = "show+ap+radio-database"
    response = aruba_show_command(wc, command, wc_api)
    for ap in response["AP Radio Database"]:
        if ap["Name"] in ap_list.keys():
            # copy the class, update it, and then put it back
            tmp = ap_list[ap["Name"]]
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
                tmp.setRadio(radio_dict)
            ap_list[ap["Name"]] = tmp
    return ap_list


def aruba_show_command(wc, command, wc_api):
    # generic show commands api query
    uid = wc_api[wc].uid
    cookie = dict(SESSION=uid)
    response = requests.get(
        url="https://" + wc + ":4343/v1/configuration/showcommand?command=" + command + "&UIDARUBA=" + uid,
        data="",
        headers={},
        cookies=cookie,
        verify=False,
    )
    return response.json()


def get_aruba_config(wc, wc_api, config_class):
    uid = wc_api[wc].uid
    cookie = dict(SESSION=uid)

    response = requests.get(
        url="https://" + wc + ":4343/v1/configuration/object/config?config_path=" + config_path + "&type=committed&UIDARUBA=" + uid,
        data="",
        headers={},
        cookies=cookie,
        verify=False,
    )
    for item in response.json()["_data"]:
        if item == "reg_domain_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateRegDomainProf(conf_dict)
        elif item == "ap_a_radio_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateRadioAProf(conf_dict)
        elif item == "ap_g_radio_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateRadioBProf(conf_dict)
        elif item == "ap_6ghz_radio_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateRadio6Prof(conf_dict)
        elif item == "ssid_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateSSIDProf(conf_dict)
        elif item == "ap_group":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateApGroup(conf_dict)
        elif item == "ap_name":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateAPName(conf_dict)
        elif item == "ap_sys_prof":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateSysProf(conf_dict)
        elif item == "virtual_ap":
            for conf in response.json()["_data"][item]:
                conf_dict = {conf["profile-name"]: conf}
                config_class.updateVirtualAP(conf_dict)
    return None

