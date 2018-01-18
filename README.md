# IVLE Sync

Fetches all files from the IVLE Workbin of all modules you are reading this
semester into the current working directory using IVLE LAPI.

Made for use with National University of Singapore's IVLE portal.

## Usage

Using Pipenv is recommended. Alternatively, you can install the packges listed in `Pipfile` in a virtualenv.

1. Install [Pipenv](https://github.com/pypa/pipenv):

```sh
pip3 install pipenv
```

2. Install dependencies:

```sh
pipenv install
```

3. Use the script:

```sh
pipenv run python ivle-sync.py
```
