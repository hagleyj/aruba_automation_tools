# aruba_automation_tools

## Table of contents
* [Setup](#setup)
* [Tools](#tools)

## Setup

Run this first to install the required python modules for your user

`pip3 install -r requirements.txt --upgrade --user`

Create the gsheet api credentials if using it
https://docs.gspread.org/en/latest/oauth2.html

Fill out constants.py with your infomation


## Tools
### aruba_ap_blink
This tool will turn on and off LED location blinking on Aruba APs by ap name or ap mac address

### aruba_ap_config
This tool allows for some structured config of arubaos AP devices, or just raw config to send to all devices

### aruba_ap_query
This tool allows for various queries of aruba controller and ap information

### aruba_ap_reboot
This tool will reboot an Aruba AP by ap name or ap mac address

### aruba_ap_rename
This tool will rename and regroup APs based on MAC address.  Can be done individually, via csv, or via Google Sheet

### aruba_wifi_user
This tool will locate a client by mac address or username.  Also allows you kick the user off the controller.  It also allows you to add and remove a user from the denylist

### aruba_backup
This is a rancid like backup tool for arubaos.  It does not have source control built in
