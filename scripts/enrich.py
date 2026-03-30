import os
import requests
import re
import unicodedata

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def clean_name(name):
    # Enlève les guillemets, virgules et espaces inutiles
    name = name.replace('"', '').replace(',', '').strip()
    # Enlève les accents (Hermès -> Hermes)
    name = "".join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    return name

def get_email(company_raw):
    company = clean_name(company_raw)
    # Liste de secours pour les noms connus
    special_cases = {"Thales": "thalesgroup.com", "Hermes": "hermes.com", "Airbus": "airbus.com"}
    
    domain = special_cases.get(company, f"{company.lower().replace(' ', '')}.com")
    
    print(f"🔎 Tentative : {company} (via {domain})")
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and res['data']['emails']:
            return res['data']['emails'][0]['value']
    except: pass
    return None

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Cette regex est beaucoup plus large pour attraper toutes tes offres
pattern = r'company:\s*"(.*?)".*?hrEmail:\s*"(.*?)"'

def replace_func(match):
    company_name = match.group(1)
    current_email = match.group(2)
    
    if not current_email.strip() or "@" not in current_email:
        email = get_email(company_name)
        if email:
            print(f"✅ Trouvé : {email}")
            # On reconstruit proprement
            return f'company: "{company_name}",\n    hrEmail: "{email}"'
    return match.group(0)

new_content = re.sub(pattern, replace_func, content, flags=re.DOTALL)

with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("🚀 Mission terminée.")
