import json
import api_utils
import os
from uuid import uuid4

def main():
    """
    Diese Funktion stellt den Server hinter der Web-App dar. Dafür wird durch die Datei api_utils.py ein Webserver gestartet.\n
    Der Webserver nimmt requests (GET, POST, DELETE) vom Client entgegen und antwortet mit responses. Diese responses können anschliessend auf dem Client verwendet werden.\n
    """
    api = api_utils.API()

    # Dateien für Nachrichten und Benutzer
    filename = "data.json"
    filenameUsers = "users.json"

    # Dateien vorbereiten falls sie noch nicht existieren
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump([], f)

    if not os.path.exists(filenameUsers):
        with open(filenameUsers, "w") as f:
            json.dump({
                "?": "Alle"
            }, f, indent=4)

    # Alle Nachrichten abrufen
    @api.GET("/api/")
    def get(request):
        with open(filename) as f:
            dataList = json.load(f)
        return dataList

    # Eine neue Nachricht hinzufügen
    @api.POST("/api/")
    def post(request, content, fromUser:str, toUser:str, type:str):
        # aktuelle Nachrichtenliste aufrufen
        with open(filename) as f:
            entryList = json.load(f)
        # Headers zur neuen Nachricht hinzufügen
        entryList.append({
                "type": type,
                "from": fromUser,
                "to": toUser,
                "content": content
            })

        # Liste aktualisieren
        with open("data.json", "w") as f:
            json.dump(entryList, f, indent=4)

        # Debug Nachricht für Client
        return f'Server: Nachricht "{content}" mit Sender "{getUsers(None)[fromUser]}" und Empfänger "{getUsers(None)[toUser]}" wurde zu den Nachrichten Hinzugefügt.'

    # Liste der Benutzer an Clients schicken
    @api.GET("/api/users/")
    def getUsers(request):
        with open(filenameUsers) as f:
            userList = json.load(f)
        
        return userList

    # Neue Benutzer abspeichern
    @api.POST("/api/users/")
    def saveUsers(request, name:str):
        newUuid = str(uuid4()) # uuid (Universal Unique IDentifier) erstellen
        with open(filenameUsers) as f:
            userList = json.load(f)
            # Benutzername wird unter dem uuid abgespeichert
            userList[newUuid] = name

        with open(filenameUsers, "w") as f:
            json.dump(userList, f, indent=4)
        
        # uuid wird an den Benutzer übergeben
        return newUuid

    # Alle Nachrichten löschen
    @api.DELETE("/api/")
    def delete(request):
        with open(filename, "w") as f:
            json.dump([], f)
        
        return f"Server: Alle Nachrichten wurden gelöscht."

    api_utils.run(api)

# Sicherstellen, dass der Server nicht durch importieren der Datei gestartet wird.
if __name__ == "__main__":
    main()
else:
    print("Dieses Skript muss ausgeführt werden, nicht importiert.")