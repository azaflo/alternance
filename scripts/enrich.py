import os, requests, re

# Récupération de la clé
API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

# Petit test de sécurité au démarrage
if not API_KEY or len(API_KEY) < 5:
    print("❌ ERREUR : La clé API Hunter est absente ou mal configurée dans les Secrets GitHub.")
    exit(1)

def get_email_by_company_name(company_name):
    # Hunter permet de chercher directement par 'company' au lieu de 'domain'
    url = f"https://api.hunter.io/v2/domain-search?company={company_name}&api_key={API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        
        # Diagnostic si l'API répond une erreur
        if response.status_code == 401:
            print(f"   ❌ Erreur 401 : Ta clé API est invalide.")
            return None
        if response.status_code == 429:
            print(f"   ❌ Erreur 429 : Quota atteint ou trop de requêtes.")
            return None
            
        res = response.json()
        emails = res.get('data', {}).get('emails', [])
        
        if not emails:
            print(f"   ⚠️ Hunter n'a trouvé aucun mail pour '{company_name}'.")
            return None

        print(f"   ✅ {len(emails)} mails trouvés pour {company_name}.")
        
        # On cherche un profil IT ou RH en priorité
        keywords = ['dsi', 'cto', 'infra', 'reseau', 'system', 'cyber', 'it', 'rh', 'hr', 'recrut', 'talent', 'job']
        for e in emails:
            profil = f"{e.get('value', '')} {e.get('position', '')}".lower()
            if any(word in profil for word in keywords):
                return e['value']
        
        # Sinon on prend le premier
        return emails[0]['value']
        
    except Exception as e:
        print(f"   ❌ Erreur de connexion : {e}")
    return None

# --- Lecture et traitement ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 Analyse de {len(matches)} offres en cours...")

found_count = 0
for match in matches:
    name = match.group(1)
    print(f"\n🔎 Recherche : {name}")
    
    email = get_email_by_company_name(name)
    if email:
        print(f"   📧 Email retenu : {email}")
        old_block = match.group(0)
        new_block = old_block.replace('hrEmail: ""', f'hrEmail: "{email}"')
        content = content.replace(old_block, new_block)
        found_count += 1

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"\n🚀 SUCCESS : {found_count} offres mises à jour !")
else:
    print("\nℹ️ Aucun changement effectué.")
