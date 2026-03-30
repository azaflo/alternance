import os
import requests
import re

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_email(company_name):
    # On définit le domaine selon l'entreprise
    domain = f"{company_name.lower().replace(' ', '')}.com"
    if "thales" in domain.lower(): domain = "thalesgroup.com"
    if "airbus" in domain.lower(): domain = "airbus.com"
    
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and res['data']['emails']:
            return res['data']['emails'][0]['value']
    except: pass
    return None

# Lecture du fichier
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

def replace_emails(match):
    company = match.group(1)
    email_val = match.group(2)
    
    # Si l'email est vide ou ne contient pas de @
    if not email_val.strip() or "@" not in email_val:
        new_email = get_email(company)
        if new_email:
            print(f"✅ Insertion de l'email pour {company} : {new_email}")
            return f'company: "{company}",\n      hrEmail: "{new_email}"'
    
    return match.group(0)

# Cette regex cherche le bloc company + hrEmail peu importe les espaces
pattern = r'company:\s*"(.*?)",\s*hrEmail:\s*"(.*?)"'
updated_content = re.sub(pattern, replace_emails, content, flags=re.DOTALL)

# Sauvegarde
with open(FILE_PATH, 'w', encoding='utf-8') as f:
    f.write(updated_content)
