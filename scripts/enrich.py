import os
import requests
import re

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_official_domain(company_name):
    """ Étape 1 : Trouve le vrai domaine de l'entreprise """
    print(f"🌐 Identification du domaine pour : {company_name}")
    # On utilise l'API de complétion de Hunter pour trouver le domaine
    url = f"https://api.hunter.io/v2/companies/suggest?name={company_name}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and len(res['data']) > 0:
            official_domain = res['data'][0]['domain']
            print(f"🎯 Domaine trouvé : {official_domain}")
            return official_domain
    except:
        pass
    return None

def get_email_from_domain(domain):
    if not domain: return None
    # On ajoute le paramètre 'department=hr' pour cibler les RH
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&department=hr&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        
        if emails:
            # On cherche en priorité un mail qui contient 'recrutement', 'hr', 'rh' ou 'jobs'
            for e in emails:
                val = e['value'].lower()
                if any(word in val for word in ['recrutement', 'rh', 'hr', 'jobs', 'career']):
                    print(f"🎯 Mail RH trouvé spécifiquement : {val}")
                    return e['value']
            
            # Si pas de mot-clé, on prend le premier mail avec le meilleur score de confiance
            if emails[0]['confidence'] > 80:
                print(f"✅ Mail à haute confiance trouvé : {emails[0]['value']}")
                return emails[0]['value']
    except:
        pass
    return None
    
# --- Logique principale ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# On cherche toutes les offres avec email vide
matches = re.finditer(r'company:\s*"(.*?)".*?hrEmail:\s*"(.*?)"', content, re.DOTALL)
found_something = False

for match in matches:
    company_name = match.group(1)
    current_email = match.group(2)
    
    if not current_email.strip() or "@" not in current_email:
        # ÉTAPE 1 : Chercher le domaine
        domain = get_official_domain(company_name)
        
        # ÉTAPE 2 : Chercher l'email
        if domain:
            email = get_email_from_domain(domain)
            if email:
                print(f"✅ Email validé : {email}")
                old_block = match.group(0)
                new_block = old_block.replace(f'hrEmail: "{current_email}"', f'hrEmail: "{email}"')
                content = content.replace(old_block, new_block)
                found_something = True

if found_something:
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print("🚀 Mise à jour terminée !")
else:
    print("Rien à enrichir pour le moment.")
