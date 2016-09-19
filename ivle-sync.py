#! /usr/bin/env python
from bs4 import BeautifulSoup
from getpass import getpass
from os import makedirs
from sys import argv
import os.path
import re
import requests

LAPI_KEY = "2urj280s9196lPJInBDNP"
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
        self.path = os.path.join(path, self.name)

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
            folder.print(indent+1)

        for file in self.files:
            print("    " * (indent+1) + file.name)

class WorkbinFile:
    def __init__(self, fileJson, path=""):
        self.name = fileJson["FileName"]
        self.id = fileJson["ID"]
        self.path = path + "/" + self.name

class IVLESession:
    def __init__(self, userid, password):
        self.userid = userid
        self.password = password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})

        self.token = self.get_token()

    def get_token(self):
        r = self.s.get("https://ivle.nus.edu.sg/api/login/?apikey=" + LAPI_KEY)
        soup = BeautifulSoup(r.content, "html.parser")

        VIEWSTATE = soup.find(id="__VIEWSTATE")['value']
        VIEWSTATEGENERATOR = soup.find(id="__VIEWSTATEGENERATOR")['value']

        data = {
                "__VIEWSTATE": VIEWSTATE,
                "__VIEWSTATEGENERATOR": VIEWSTATEGENERATOR,
                "userid": self.userid,
                "password": self.password
            }

        r = self.s.post("https://ivle.nus.edu.sg/api/login/?apikey=" + LAPI_KEY, data)
        return r.text

    def get_modules(self):
        result = self.lapi("Modules")

        modules = []
        for module in result["Results"]:
            modules.append(Module(
                    module["ID"],
                    module["CourseName"],
                    module["CourseCode"]
                ))
        return modules

    def get_workbin(self, module):
        result = self.lapi("Workbins", {"CourseID": module.id})

        folders = []
        for workbin in result["Results"]:
            for folder in workbin["Folders"]:
                folders.append(WorkbinFolder(folder, module.code))
        return folders

    def lapi(self, method, params={}):
        params["APIKey"] = LAPI_KEY
        params["AuthToken"] = self.token
        return self.s.get("https://ivle.nus.edu.sg/api/Lapi.svc/" + method,
            params=params).json()

    def download_file(self, file):
        params = {
                    "APIKey": LAPI_KEY,
                    "AuthToken": self.token,
                    "ID": file.id,
                    "target": "workbin"
                }

        makedirs(os.path.dirname(file.path), exist_ok=True)

        r = None
        if os.path.isfile(file.path):
            r = self.s.get("https://ivle.nus.edu.sg/api/downloadfile.ashx",
                    stream=True, params=params)
            # print("Skipping " + file.path + ".")
            return

        print("Downloading " + file.path + ".")
        with open(file.path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)

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

def main():

    if argv[1] == "files" or argv[1] == "f":
        userid = input("UserID: ")
        password = getpass("Password: ")
        session = IVLESession(userid, password)
        sync_files(session)

    elif argv[1] == "announcements" or argv[1] == "a":
        userid = input("UserID: ")
        password = getpass("Password: ")
        session = IVLESession(userid, password)
        sync_announcements(session)

    else:
        print("Usage: " + argv[0] + " [files|announcements]")

if __name__ == "__main__":
    main()
