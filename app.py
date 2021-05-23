import json
import api_utils
import os

api = api_utils.API()
filename = "data.json"

# prepare data.json if it doesn't exist
if not os.path.exists(filename):
    with open(filename, "w") as f:
        json.dump([], f)
        f.close()

@api.GET("/api/")
def get(request):
    # get current list and send to webpage
    with open(filename) as f:
        entryList = json.load(f)
        f.close()
    return entryList

@api.POST("/api/")
def post(request, text:str, name:str):
    # get current list and add new element with username
    with open(filename) as f:
        entryList = json.load(f)
        f.close()
    entryList.append(f"{name}: {text}")

    # dump new list into data.json
    with open("data.json", "w") as f:
        json.dump(entryList, f, indent=4)
        f.close()

    return None

# clear list
@api.DELETE("/api/")
def delete(request):
    with open(filename, "w") as f:
        json.dump([], f)
        f.close()

api_utils.run(api)