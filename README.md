# One Stoop UI

## About One Stoop
The goal of One Stoop is to create an open social media platform.  Open can mean different things so lets be clear.  For us open starts with being a nonprofit company (there is no company yet, still in the formation phase).  It also means we will be open with all our goals and activities.  Finally we are open with our code.  Its all here for you to see and help with.

Being nonprofit here are some of our goals and activities.
* Rule number one, never share or sell a users personal data.  End users are not the product, the platform is.
* Any advertisements on the site will not use personal data to target users.
* We will operate mostly on donations

## About os-api
os-api is the API interface for One Stoop.  The main components of os-api are written using Python with the Flask framework.

### Goals for os-ui
* Be secure, don't leak data
* Be light and easy to use

# Getting started with One Stoop
## Local Build Setup
You will need [os-api](https://github.com/OneStoop/os-api) and [os-ui](https://github.com/OneStoop/os-ui).  Please see each repo for instructions on setup of that service.

Prerequisites:
1) Python 3.6 or greater.
2) A firebase account [https://firebase.google.com/](https://firebase.google.com/)
Authentication should be enabled with at least Email/Password sign-in method
3) A IBM Cloud account [https://cloud.ibm.com/](https://cloud.ibm.com/) with Cloud Object Storage provisioned

Steps:
1) Clone this repo: `git clone git@github.com:OneStoop/os-api.git`
2) Convert closed directory to a virtualenv `virtualenv -p python3 os-ap`
3) Change to cloned directory and install packages: `cd os-api/ && bin/pip install -r requirements.txt`
4) Create a `config.py` file.  Copy the content of config.py.template to config.py and update with your account information.
5) Create an env variable for PORT `PORT=5001`.  Export this `export PORT`

``` bash
# serve at localhost:5001
bin/uwsgi -i server.ini
```

# Questions? Need Help? Found a bug?
For now create an issue
