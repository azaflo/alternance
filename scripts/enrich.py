import os
import requests
import re

# Configuration
API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_email(company_name):
    if not API_KEY: return None
    # Nettoyage simple du domaine
    domain = company_name.lower().replace(' ', '').replace('é', 'e').replace('è', 'e')
    if "thales" in domain: domain = "thalesgroup.com"
    if "airbus" in domain: domain = "airbus.com"
    if "." not in domain: domain += ".com"
    
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and res['data']['emails']:
            return res['data']['emails'][0]['value']
    except: pass
    return None

if not os.path.exists(FILE_PATH):
    print("Fichier index.html introuvable")
    exit(1)

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# On utilise une fonction de remplacement plus propre pour éviter l'erreur de groupe
def replace_func(match):
    full_block = match.group(0)
    company = match.group(1)
    email_val = match.group(2)
    
    # Si le champ email est vide
    if not email_val.strip() or "@" not in email_val:
        print(f"🔎 Recherche pour : {company}")
        found_email = get_email(company)
        if found_email:
            print(f"✅ Trouvé : {found_email}")
            # On reconstruit la ligne proprement sans utiliser de backreferences complexes
            return f'company: "{company}",\n      hrEmail: "{found_email}"'
    
    return full_block

# La regex cherche : company: "NOM", (retour à la ligne) hrEmail: "VALEUR"
pattern = r'company:\s*"(.*?)",\s*hrEmail:\s*"(.*?)"'
new_content = re.sub(pattern, replace_func, content, flags=re.DOTALL)

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Terminé avec succès.")
