import api_utils;
from datetime import datetime as dt
from random import randint

api = api_utils.API()

@api.GET("/api")
def hello_world(request):
    return f"   ---   Hello World   ---   Random number: {randint(1, 100)}   ---   Time: {dt.now().hour}:{dt.now().minute}:{dt.now().second}   ---   "

api_utils.run(api)