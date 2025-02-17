import requests
import urllib.parse

# Ta clé API Riot
api_key = "RGAPI-7cfa4c37-aa4f-43fc-badd-f4b664791527"

# Ton Riot ID (pseudo) et ton tag
game_name = "Nikkodinho"
tag_line = "#HAN"  # le tag, avec le caractère '#' inclus

# Encodage du tag pour l'URL (le '#' devient '%23')
tag_line_enc = urllib.parse.quote(tag_line)

# Construction de l'URL pour récupérer les informations du compte Riot
url = f"https://api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line_enc}"

# Définition des headers avec la clé API
headers = {
    "X-Riot-Token": api_key
}

# Envoi de la requête GET
response = requests.get(url, headers=headers)

# Traitement de la réponse
if response.status_code == 200:
    data = response.json()
    puuid = data.get("puuid")
    print("PUUID :", puuid)
else:
    print("Erreur :", response.status_code, response.text)
