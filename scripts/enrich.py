import os, requests, re, unicodedata

API_KEY = os.getenv("HUNTER_API_KEY")
FILE_PATH = "index.html"

def get_official_domain(company_name):
    # Nettoyage des accents
    clean_name = "".join(c for c in unicodedata.normalize('NFD', company_name) if unicodedata.category(c) != 'Mn')
    
    # CORRECTIF : On ajoute l'API_KEY ici aussi !
    url = f"https://api.hunter.io/v2/companies/suggest?name={clean_name}&api_key={API_KEY}"
    
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('data') and len(res['data']) > 0:
            dom = res['data'][0]['domain']
            print(f"   🌐 Domaine identifié : {dom}")
            return dom
    except: pass
    print(f"   ⚠️ Impossible de trouver le domaine pour {company_name} (Vérifie ta clé API)")
    return None

def get_email_from_domain(domain):
    if not domain: return None
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        emails = res.get('data', {}).get('emails', [])
        print(f"   📦 Hunter a trouvé {len(emails)} mails au total.")
        
        if not emails: return None

        # Filtre intelligent : Priorité aux RH et à l'IT (SISR/Licence)
        keywords = ['dsi', 'cto', 'infra', 'reseau', 'system', 'cyber', 'it', 'rh', 'hr', 'recrut', 'talent', 'job', 'contact']

        for e in emails:
            email_val = e.get('value', '').lower()
            position = (e.get('position') or "").lower()
            profil = f"{email_val} {position}"

            if any(word in profil for word in keywords):
                print(f"   🎯 Cible trouvée : {email_val} ({position})")
                return e['value']
        
        # Secours : on prend le 1er mail si bon score
        return emails[0]['value']
            
    except: pass
    return None

# --- Logique principale ---
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r'company:\s*"(.*?)".*?hrEmail:\s*""'
matches = list(re.finditer(pattern, content, re.DOTALL))

print(f"📊 {len(matches)} offres vides détectées. Lancement...")

found_count = 0
for match in matches:
    company_name = match.group(1)
    print(f"\n🔎 TRAVAIL SUR : {company_name}")
    
    domain = get_official_domain(company_name)
    if domain:
        email = get_email_from_domain(domain)
        if email:
            old_text = match.group(0)
            new_text = old_text.replace('hrEmail: ""', f'hrEmail: "{email}"')
            content = content.replace(old_text, new_text)
            found_count += 1

if found_count > 0:
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"\n🚀 TERMINE : {found_count} mails injectés !")
else:
    print("\nℹ️ Aucun mail trouvé (Vérifie tes crédits Hunter.io)")
