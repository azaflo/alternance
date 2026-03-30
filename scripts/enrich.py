import os
import requests
import re

# 1. Config (La clé est récupérée via le Secret GitHub)
API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_email(domain):
    if not API_KEY or not domain: return None
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and res['data']['emails']:
            return res['data']['emails'][0]['value']
    except:
        pass
    return None

# 2. Lecture du fichier index.html
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 3. Extraction des entreprises (on cherche le champ 'company')
# On cible le format : company: "Nom",
companies = re.findall(r'company:\s*"(.*?)"', content)

updated_content = content

for company in companies:
    # On détermine le domaine (tu peux enrichir cette liste)
    domain = f"{company.lower().replace(' ', '')}.com"
    if "thales" in domain: domain = "thalesgroup.com"
    
    # On vérifie si l'email est vide pour cette entreprise précise
    # On cherche le bloc spécifique à cette entreprise pour ne pas se tromper
    pattern = rf'(company:\s*"{re.escape(company)}".*?hrEmail:\s*")(")'
    
    # Si on trouve un hrEmail vide après cette entreprise
    if re.search(pattern, updated_content, re.DOTALL):
        print(f"🔎 Recherche d'email pour : {company} ({domain})...")
        email_trouve = get_email(domain)
        
        if email_trouve:
            print(f"✅ Trouvé : {email_trouve}")
            # Remplacement dans le texte
            updated_content = re.sub(pattern, rf'\1{email_trouve}\3', updated_content, flags=re.DOTALL)

# 4. Sauvegarde des modifications
with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(updated_content)

print("🚀 Mission terminée : index.html mis à jour.")
