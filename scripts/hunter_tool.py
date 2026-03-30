import requests
import sys

# Ta clé API Hunter.io
API_KEY = "b650dd3a188b7ae35f3cf7963181945410e1a536"

def find_email(company_domain):
    url = f"https://api.hunter.io/v2/domain-search?domain={company_domain}&api_key={API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('data') and data['data']['emails']:
            # On récupère le premier email trouvé
            return data['data']['emails'][0]['value']
        return "Aucun email public trouvé"
    except Exception as e:
        return f"Erreur API: {str(e)}"

if __name__ == "__main__":
    # Permet à l'agent de passer le domaine en argument
    if len(sys.argv) > 1:
        domain = sys.argv[1]
        print(find_email(domain))
