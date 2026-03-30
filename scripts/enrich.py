import os
import requests
import json

# On récupère la clé depuis les secrets GitHub, pas en dur !
API_KEY = os.getenv("HUNTER_API_KEY")

def get_email(domain):
    if not API_KEY: return None
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    res = requests.get(url).json()
    return res['data']['emails'][0]['value'] if res.get('data') and res['data']['emails'] else None

# Ici on pourrait ajouter la logique pour lire index.html et le mettre à jour
print("Script prêt pour l'automatisation via GitHub Actions")
