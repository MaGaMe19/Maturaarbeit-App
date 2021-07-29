import json
import api_utils
import os
from uuid import uuid4

api = api_utils.API()

# files
filename = "data.json"
filenameUsers = "users.json"

# prepare data.json if it doesn't exist
if not os.path.exists(filename):
    with open(filename, "w") as f:
        json.dump([], f)

# prepare users.json if it doesn't exist
if not os.path.exists(filenameUsers):
    with open(filenameUsers, "w") as f:
        json.dump({
            "?": "Alle"
        }, f, indent=4)

@api.GET("/api/")
def get(request):
    # get current datalist
    with open(filename) as f:
        dataList = json.load(f)
    return dataList

@api.POST("/api/")
def post(request, content, fromUser:str, toUser:str, type:str):
    # get current list and add new element
    with open(filename) as f:
        entryList = json.load(f)
    # construct message with headers
    entryList.append({
            "type": type,
            "from": fromUser,
            "to": toUser,
            "content": content
        })

    # dump updated list into data.json
    with open("data.json", "w") as f:
        json.dump(entryList, f, indent=4)

    return None

# return userList to front-end for connections
@api.GET("/api/users/")
def getUsers(request):
    with open(filenameUsers) as f:
        userList = json.load(f)
    
    return userList

# collect users
@api.POST("/api/users/")
def saveUsers(request, name:str):
    newUuid = str(uuid4()) # create uuid (Universal Unique IDentification)
    with open(filenameUsers) as f:
        userList = json.load(f)
        # save username as value with the uuid as key
        userList[newUuid] = name

    with open(filenameUsers, "w") as f:
        json.dump(userList, f, indent=4)
    
    # return uuid that it can be stored locally in the browser
    return newUuid

# clear list
@api.DELETE("/api/")
def delete(request):
    with open(filename, "w") as f:
        json.dump([], f)

api_utils.run(api)