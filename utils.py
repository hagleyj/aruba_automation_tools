#!/usr/bin/env python3
from netaddr import *
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from constants import *


class utils:
    def __init__(self) -> None:
        pass

    def dotdec2hex(dotdec):
        """convert dotted decimal to hex"""
        hexlist = []
        for decimal in dotdec.split("."):
            d = int(decimal)
            if d < 0 or d > 255:
                print(dotdec, "is not a valid dotted decimal")
                return None
            h = format(d, "02x")
            hexlist.append(h)
        hexout = ":".join(hexlist)
        return hexout

    def hex2dotdec(mac):
        """convert hex to dotted decimal"""
        hexlist = []
        for h in mac.split(":"):
            d = int(h, 16)
            hexlist.append(str(d))
        dotdecout = ".".join(hexlist)
        return dotdecout

    def mac_to_colon_separated(mac):
        eui_mac = EUI(mac)
        eui_mac.dialect = mac_unix_expanded
        return str(eui_mac).upper()


class GoogleSheet(object):
    def __init__(self):
        self.scope_app = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        self.service_account_email = SERVICE_ACCOUNT_EMAIL

        self.project_id = PROJECT_ID
        self.client_id = CLIENT_ID
        self.private_key_id = PRIVATE_KEY_ID
        self.private_key = PRIVATE_KEY

    def _gsheet_auth(self):
        json_creds = {
            "type": "service_account",
            "project_id": self.project_id,
            "private_key_id": self.private_key_id,
            "private_key": self.private_key,
            "client_email": self.service_account_email,
            "client_id": self.client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/" + self.service_account_email.replace("@", "%40"),
        }
        cred = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, self.scope_app)

        # authorize the clientsheet
        return gspread.authorize(cred)

    def open_google_sheet(self, sheet_id, sheet_num):
        client = self._gsheet_auth()
        sheet = client.open_by_key(sheet_id)

        sheet_instance = sheet.get_worksheet(sheet_num)

        # return a list of dictionaries.  Each list entry is a row, with the keys being the column headers
        return sheet_instance.get_all_records()
