#! /usr/bin/env python3
from bs4 import BeautifulSoup
from getpass import getpass
from os import makedirs, remove
from sys import argv, exit
from os.path import join, dirname, isfile, realpath
import re
import requests
import json
import argparse

# Fill up ./credentials.json with your LAPI key
# http://ivle.nus.edu.sg/LAPI/default.aspx
with open(
        join(dirname(realpath(__file__)), 'credentials.json'),
        encoding='utf-8') as file:
    credentials = json.loads(file.read())

USER_AGENT = "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.120 Safari/537.36"


class Module:
    def __init__(self, moduleId, name, code):
        self.id = moduleId
        self.name = name
        self.code = code.replace('/', '-')


class Webcast:
    def __init__(self, title, url, module):
        self.title = title
        self.url = url
        self.module = module


class WorkbinFolder:
    def __init__(self, folderJson, path=""):
        self.name = folderJson["FolderName"]
        self.id = folderJson["ID"]
        self.path = join(path, self.name)

        self.folders = []
        for fileJson in folderJson["Folders"]:
            self.folders.append(WorkbinFolder(fileJson, self.path))

        self.files = []
        for fileJson in folderJson["Files"]:
            self.files.append(WorkbinFile(fileJson, self.path))

    def printPath(self):
        print(self.path)

        for folder in self.folders:
            folder.printPath()

        for file in self.files:
            print(file.path)

    def print(self, indent=0):
        print("    " * indent + self.name + "/")

        for folder in self.folders:
            folder.print(indent + 1)

        for file in self.files:
            print("    " * (indent + 1) + file.name)


class WorkbinFile:
    def __init__(self, fileJson, path=""):
        self.name = fileJson["FileName"]
        self.id = fileJson["ID"]
        self.path = join(path, self.name)


class IVLESession:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})

        self.token = self.get_token()
        if self.token == '':
            print("Login failed, please check your NUSNET UserID and password")

    def get_token(self):
        try:
            self.token = ""
            r = self.lapi("Validate", {"Token": credentials['TOKEN']})
            if not r['Success']:
                clear_token()
                return self.get_new_token()

            if r['Token'] != credentials['TOKEN']:
                credentials['TOKEN'] = r['Token']
                write_credentials()
            return r['Token']

        except KeyError:
            return self.get_new_token()

    def get_new_token(self):
        r = self.s.get("https://ivle.nus.edu.sg/api/login/?apikey=" +
                       credentials['LAPI_KEY'])
        soup = BeautifulSoup(r.content, "html.parser")

        VIEWSTATE = soup.find(id="__VIEWSTATE")['value']
        VIEWSTATEGENERATOR = soup.find(id="__VIEWSTATEGENERATOR")['value']

        userid, password = get_credentials()

        data = {
            "__VIEWSTATE": VIEWSTATE,
            "__VIEWSTATEGENERATOR": VIEWSTATEGENERATOR,
            "userid": userid,
            "password": password
        }

        r = self.s.post("https://ivle.nus.edu.sg/api/login/?apikey=" +
                        credentials['LAPI_KEY'], data)

        if len(r.text) > 1000:  # hacky way to check if return is a HTML page
            return ''

        credentials['TOKEN'] = r.text
        write_credentials()

        return r.text

    def get_modules(self):
        result = self.lapi("Modules")

        modules = []
        for module in result["Results"]:
            modules.append(
                Module(module["ID"], module["CourseName"],
                       module["CourseCode"]))
        return modules

    def get_workbin(self, module):
        result = self.lapi("Workbins", {"CourseID": module.id})

        folders = []
        for workbin in result["Results"]:
            for folder in workbin["Folders"]:
                folders.append(WorkbinFolder(folder, module.code))
        return folders

    def get_webcasts(self, module):
        result = self.lapi("Webcasts", {"CourseID": module.id})

        webcasts = []
        for webcast in result["Results"]:
            for itemGroup in webcast['ItemGroups']:
                for video in itemGroup['Files']:
                    webcasts.append(
                        Webcast(video['FileTitle'], video['MP4'], module))
        return webcasts

    def lapi(self, method, params={}):
        params["APIKey"] = credentials['LAPI_KEY']
        params["AuthToken"] = self.token
        return self.s.get(
            "https://ivle.nus.edu.sg/api/Lapi.svc/" + method,
            params=params).json()

    def download_webcast(self, webcast):
        cookies = {'.ASPXAUTH': 'a 480 characters long hash'}

        print("Downloading " + webcast.title + ".")
        r = self.s.get(webcast.url, stream=True, cookies=cookies)

        if isfile(webcast.title):
            return

        try:
            with open(webcast.title, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        except:
            os.remove(webcast.title)

    def download_file(self, file):
        params = {
            "APIKey": credentials['LAPI_KEY'],
            "AuthToken": self.token,
            "ID": file.id,
            "target": "workbin"
        }

        makedirs(dirname(file.path), exist_ok=True)

        if isfile(file.path):
            return

        print("Downloading " + file.path)
        r = self.s.get(
            "https://ivle.nus.edu.sg/api/downloadfile.ashx",
            stream=True,
            params=params)

        try:
            with open(file.path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        except:
            remove(file.path)

    def download_folder(self, target_folder):
        for folder in target_folder.folders:
            self.download_folder(folder)

        for file in target_folder.files:
            self.download_file(file)


def sync_files(session):
    modules = session.get_modules()

    for module in modules:
        print("=== " + module.code + ": " + module.name + " ===")

        folders = session.get_workbin(module)
        for folder in folders:
            session.download_folder(folder)
        print()


def sync_announcements(session):
    modules = session.get_modules()

    DURATION = 60 * 24 * 5

    for module in modules:
        print("=== " + module.code + ": " + module.name + " ===")

        announcements = session.lapi("Announcements", {
            "CourseID": module.id,
            "Duration": DURATION
        })
        for announcement in announcements["Results"]:
            print("== " + announcement["Title"] + " ==")

            description = BeautifulSoup(announcement["Description"],
                                        "html.parser").get_text()
            description = re.sub(r'\n\s*\n', '\n', description)
            print(description)
            print()
        print()


def sync_webcasts(session):
    modules = session.get_modules()

    for module in modules:
        webcasts = session.get_webcasts(module)
        for webcast in webcasts:
            session.download_webcast(webcast)


def get_credentials():
    userid = credentials['USERID']
    if userid == '':
        userid = input("NUSNET UserID: ")

    password = credentials['PASSWORD']
    if password == '':
        password = getpass("Password: ")

    if (credentials['USERID'] == '' or
            credentials['PASSWORD'] == '') and ask_whether_write_credentials():
        credentials['USERID'] = userid
        credentials['PASSWORD'] = password
        write_credentials()

    return (userid, password)


def get_lapi_key():
    print(
        "Generate your LAPI key from http://ivle.nus.edu.sg/LAPI/default.aspx")
    while True:
        lapi_key = input("LAPI key:")
        if lapi_key != '':
            return lapi_key


def clear_token():
    try:
        del credentials['TOKEN']
        write_credentials()
        print("Logged out.")
    except:
        print("Not logged in.")
        exit(1)


def write_credentials():
    try:
        with open(
                join(dirname(realpath(__file__)), 'credentials.json'),
                'w',
                encoding='utf-8') as file:
            json.dump(credentials, file)

    except:
        print("Error writing to credentials.json")
        exit(1)


def ask_whether_write_credentials():
    yes = set(['yes', 'y'])
    no = set(['no', 'n', ''])

    while True:
        choice = input(
            "Do you want us to remember your NUSNET UserID and password? [y/N] "
        ).lower()
        if choice in yes:
            return True
        elif choice in no:
            return False
        else:
            print("Please respond with 'yes' or 'no'")


def parse_args():
    parser = argparse.ArgumentParser(usage="%(prog)s <action> [arguments]")
    subparsers = parser.add_subparsers(title="Actions", dest='action')

    # parser_v = parser.add_argument("-v", "--verbose", help="Verbose mode")

    parser_f = subparsers.add_parser(
        "files",
        aliases=['f'],
        help="Sync IVLE files to the current directory")
    # parser_f.add_argument("-d", "--directory", help="Store files in DIRECTORY")

    parser_a = subparsers.add_parser(
        "announcements", aliases=['a'], help="Print out IVLE announcements")

    parser_w = subparsers.add_parser(
        "webcasts", aliases=['w'], help="Sync Panopto web lectures to the current directory")

    parser_l = subparsers.add_parser(
        "logout", aliases=['l'], help="Logout and clear token")

    if len(argv) == 1:  # if given no arguments
        parser.print_help()
        exit(1)

    return parser.parse_args()


def main():

    try:
        args = parse_args()

        if credentials['LAPI_KEY'] == '':
            credentials['LAPI_KEY'] = get_lapi_key()
            write_credentials()

        if args.action == "files" or args.action == "f":
            # base_dir = args.directory
            session = IVLESession()
            sync_files(session)
        elif args.action == "announcements" or args.action == "a":
            session = IVLESession()
            sync_announcements(session)
        elif args.action == "webcasts" or args.action == "w":
            session = IVLESession()
            sync_webcasts(session)
        elif args.action == "logout" or args.action == "l":
            clear_token()

        print("Finished!")
        exit(0)

    except (requests.exceptions.RequestException):
        print("Error: Connection refused.")
        exit(1)

    except (KeyboardInterrupt):
        print("Aborting...")
        exit(1)


if __name__ == "__main__":
    main()
