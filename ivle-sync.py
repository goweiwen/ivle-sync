#! /usr/bin/env python3
from bs4 import BeautifulSoup
from getpass import getpass
from os import makedirs
from sys import argv, exit
from os.path import join, dirname, isfile, realpath
import re
import requests
import json

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
        self.code = code


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
            folder. print(indent + 1)

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
            print("Login fail, please check your userid and password")

    def get_token(self):
        try:
            self.token = ""
            r = self.lapi("Validate", {"Token": credentials['TOKEN']})
            if not r["Success"]:
                print("Invalid token")
                clear_token()
                return self.new_token()

            if r['Token'] != credentials['TOKEN']:
                print(
                    "New token obtained -- old token is expiring in one day.")
                credentials['TOKEN'] = r['Token']
                write_credentials()
            return r['Token']

        except KeyError:
            return self.new_token()

    def new_token(self):
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
        if yes_no():
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

    def lapi(self, method, params={}):
        params["APIKey"] = credentials['LAPI_KEY']
        params["AuthToken"] = self.token
        return self.s.get(
            "https://ivle.nus.edu.sg/api/Lapi.svc/" + method,
            params=params).json()

    def download_file(self, file):
        params = {
            "APIKey": credentials['LAPI_KEY'],
            "AuthToken": self.token,
            "ID": file.id,
            "target": "workbin"
        }

        makedirs(dirname(file.path), exist_ok=True)

        if isfile(file.path):
            # print("Skipping " + file.path + ".")
            return

        print("Downloading " + file.path + ".")
        r = self.s.get(
            "https://ivle.nus.edu.sg/api/downloadfile.ashx",
            stream=True,
            params=params)

        try:
            with open(file.path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        except:
            os.remove(file.path)

    def download_folder(self, target_folder):
        for folder in target_folder.folders:
            self.download_folder(folder)

        for file in target_folder.files:
            self.download_file(file)


def sync_files(session):
    modules = session.get_modules()

    for module in modules:
        folders = session.get_workbin(module)
        for folder in folders:
            session.download_folder(folder)


def sync_announcements(session):
    modules = session.get_modules()

    DURATION = 60 * 24 * 5

    for module in modules:
        announcements = session.lapi("Announcements", {
            "CourseID": module.id,
            "Duration": DURATION
        })
        for announcement in announcements["Results"]:
            print("\n\n\n")
            print("=== " + announcement["Title"] + " ===")
            description = BeautifulSoup(announcement["Description"],
                                        "html.parser").get_text()
            description = re.sub(r'\n\s*\n', '\n', description)
            print(description)
            input()


def get_credentials():
    userid = input("UserID: ")

    password = getpass("Password: ")

    return (userid, password)


def clear_token():
    try:
        del credentials['TOKEN']
        write_credentials()
        print("Token cleared.")
    except:
        print("No token is set.")
        exit(-1)


def write_credentials():
    try:
        with open(
                join(dirname(realpath(__file__)), 'credentials.json'),
                'w',
                encoding='utf-8') as file:
            json.dump(credentials, file)

    except:
        print("Error writing to credentials.json")
        exit(-1)


def yes_no():
    yes = set(['yes', 'y'])
    no = set(['no', 'n'])

    while True:
        choice = input(
            "Do you want to write the token obtained to credentials.json?[y/n] "
        ).lower()
        if choice in yes:
            return True
        elif choice in no:
            return False
        else:
            print("Please respond with 'yes' or 'no'")


def main():

    if credentials['LAPI_KEY'] == '':
        print("Fill up ./credentials.json with your LAPI key")
        print("http://ivle.nus.edu.sg/LAPI/default.aspx")
        exit(1)

    try:
        if len(argv) > 1:
            if argv[1] == "files" or argv[1] == "f":
                session = IVLESession()
                if session.token != '':
                    sync_files(session)
            elif argv[1] == "announcements" or argv[1] == "a":
                session = IVLESession()
                if session.token != '':
                    sync_announcements(session)
            elif argv[1] == "clear-token" or argv[1] == "c":
                clear_token()
            exit(1)

    except (requests.exceptions.RequestException):
        print("Error: Connection refused.")
        exit(-1)

    except (KeyboardInterrupt, SystemExit):
        print("Aborting...")
        exit(-1)

    print("Usage: " + argv[0] + " [files|announcements|clear-token]")


if __name__ == "__main__":
    main()
