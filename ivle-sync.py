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
            folder.print(indent + 1)

        for file in self.files:
            print("    " * (indent + 1) + file.name)


class WorkbinFile:
    def __init__(self, fileJson, path=""):
        self.name = fileJson["FileName"]
        self.id = fileJson["ID"]
        self.path = join(path, self.name)


class IVLESession:
    def __init__(self, userid, password):
        self.userid = userid
        self.password = password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})

        self.token = self.get_token()
        if self.token == '':
            print("Login fail, please check your userid and password")

    def get_token(self):
        r = self.s.get("https://ivle.nus.edu.sg/api/login/?apikey=" +
                       credentials['LAPI_KEY'])
        soup = BeautifulSoup(r.content, "html.parser")

        VIEWSTATE = soup.find(id="__VIEWSTATE")['value']
        VIEWSTATEGENERATOR = soup.find(id="__VIEWSTATEGENERATOR")['value']

        data = {
            "__VIEWSTATE": VIEWSTATE,
            "__VIEWSTATEGENERATOR": VIEWSTATEGENERATOR,
            "userid": self.userid,
            "password": self.password
        }

        r = self.s.post("https://ivle.nus.edu.sg/api/login/?apikey=" +
                        credentials['LAPI_KEY'], data)

        if len(r.text) > 1000:  # hacky way to check if return is a HTML page
            return ''

        return r.text

    def get_modules(self):
        result = self.lapi("Modules")

        modules = []
        for module in result["Results"]:
            modules.append(
                Module(module["ID"], module["CourseName"], module[
                    "CourseCode"]))
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

    def download_file(self, file, base_dir):
        params = {
            "APIKey": credentials['LAPI_KEY'],
            "AuthToken": self.token,
            "ID": file.id,
            "target": "workbin"
        }

        file.path = base_dir + file.path

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

    def download_folder(self, target_folder, base_dir):
        for folder in target_folder.folders:
            self.download_folder(folder, base_dir)

        for file in target_folder.files:
            self.download_file(file, base_dir)


def sync_files(session, base_dir):
    modules = session.get_modules()

    for module in modules:
        folders = session.get_workbin(module)
        for folder in folders:
            session.download_folder(folder, base_dir)


def sync_announcements(session):
    modules = session.get_modules()

    DURATION = 60 * 24 * 5

    for module in modules:
        announcements = session.lapi(
            "Announcements", {"CourseID": module.id,
                              "Duration": DURATION})
        for announcement in announcements["Results"]:
            print("\n\n\n")
            print("=== " + announcement["Title"] + " ===")
            description = BeautifulSoup(announcement["Description"],
                                        "html.parser").get_text()
            description = re.sub(r'\n\s*\n', '\n', description)
            print(description)
            input()


def get_credentials():
    userid = credentials['USERID']
    if userid == '':
        userid = input("UserID: ")

    password = credentials['PASSWORD']
    if password == '':
        password = getpass("Password: ")

    return (userid, password)

def collect(argv):
    args = {}
    while argv:
        if argv[0][0] == '-':
            args[argv[0]] = argv[1]
        argv = argv[1:]
    return args

def main():

    if credentials['LAPI_KEY'] == '':
        print("Fill up ./credentials.json with your LAPI key")
        print("http://ivle.nus.edu.sg/LAPI/default.aspx")
        exit(1)

    args = collect(argv)
    base_dir = ""
    try:
        if '-d' in args:
            base_dir = args['-d'];
            if not base_dir.endswith('/'):
                base_dir = base_dir + '/'
            print("-d found, placing file in: " + base_dir + "<course code>")
        if '-f' in args:
            userid, password = get_credentials()
            session = IVLESession(userid, password)
            if session.token != '':
                sync_files(session, base_dir)
        if '-a' in args:
            userid, password = get_credentials()
            session = IVLESession(userid, password)
            if session.token != '':
                sync_announcements(session)
    # try:
    #     if len(argv) > 1:
    #         if argv[1] == "files" or argv[1] == "f":
    #             userid, password = get_credentials()
    #             session = IVLESession(userid, password)
    #             if session.token != '':
    #                 sync_files(session)
    #         elif argv[1] == "announcements" or argv[1] == "a":
    #             userid, password = get_credentials()
    #             session = IVLESession(userid, password)
    #             if session.token != '':
    #                 sync_announcements(session)
    #         exit(1)

    except (requests.exceptions.RequestException):
        print("Error: Connection refused.")
        exit(-1)

    except (KeyboardInterrupt, SystemExit):
        print("Aborting...")
        exit(-1)

    # print("Usage: " + argv[0] + " [files|announcements]")
    print("Usage: " + argv[0] )
    print("  -f for files. ")
    print("  -a for announcements. ")
    print("  -d <directory> to output files to a different directory. ")


if __name__ == "__main__":
    main()
