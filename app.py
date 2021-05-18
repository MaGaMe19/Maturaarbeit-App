import api_utils;
from datetime import datetime as dt
from random import randint

api = api_utils.API()

@api.GET("/api/")
def hello_world(request):
    return "Hello World"

@api.POST("/api/")
def toUpper(request, text:str):
    return text.upper()

api_utils.run(api)