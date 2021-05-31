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
        json.dump({}, f)

@api.GET("/api/")
def get(request):
    # get current userlist to look up names
    with open (filenameUsers) as f:
        userList = json.load(f)
    # get current datalist
    with open(filename) as f:
        dataList = json.load(f)
        messageList = [] # construct separate list for formatted messages
        for listEntry in dataList:
            # look up names in userList and format message accordingly
            messageList.append(f'{userList[listEntry["from"]]} -> {userList[listEntry["to"]]}: {listEntry["message"]}')
    return messageList

@api.POST("/api/")
def post(request, text:str, fromUser:str, toUser:str):
    # get current list and add new element
    with open(filename) as f:
        entryList = json.load(f)
    # construct message with headers
    entryList.append(
        {
            "from": fromUser,
            "to": toUser,
            "message": text
        }
    )

    # dump updated list into data.json
    with open("data.json", "w") as f:
        json.dump(entryList, f, indent=4)

    return None

# collect users
@api.POST("/api/names/")
def saveUser(request, name:str):
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