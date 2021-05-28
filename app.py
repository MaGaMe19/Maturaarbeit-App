import json
import api_utils
import os
from uuid import uuid4

api = api_utils.API()
filename = "data.json"
filenameUsers = "users.json"

# prepare data.json if it doesn't exist
if not os.path.exists(filename):
    with open(filename, "w") as f:
        json.dump([], f)

if not os.path.exists(filenameUsers):
    with open(filenameUsers, "w") as f:
        json.dump({}, f)

@api.GET("/api/")
def get(request):
    # get current list and send to webpage
    with open(filename) as f:
        entryList = json.load(f)
    return entryList

@api.POST("/api/")
def post(request, text:str, name:str):
    # get current list and add new element with username
    with open(filename) as f:
        entryList = json.load(f)
    entryList.append(f"{name}: {text}")

    # dump new list into data.json
    with open("data.json", "w") as f:
        json.dump(entryList, f, indent=4)

    return None

@api.POST("/api/names/")
def saveUser(request, name:str):
    newUuid = str(uuid4())
    with open(filenameUsers) as f:
        userList = json.load(f)
        userList[newUuid] = name

    with open(filenameUsers, "w") as f:
        json.dump(userList, f, indent=4)
    
    return newUuid

# clear list
@api.DELETE("/api/")
def delete(request):
    with open(filename, "w") as f:
        json.dump([], f)

api_utils.run(api)