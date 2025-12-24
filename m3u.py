import requests
import os
import re
import json
import sys
import time
import urllib.parse
import urllib3
import concurrent.futures
from datetime import datetime, timedelta
from base64 import b64decode, b64encode
from binascii import a2b_hex

try:
    from bs4 import BeautifulSoup
    from dateutil import parser
    from playwright.sync_api import sync_playwright
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: Missing required libraries. Please run: pip install requests beautifulsoup4 python-dateutil playwright", file=sys.stderr)

# Disabilita gli avvisi di sicurezza per le richieste senza verifica SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def headers_to_extvlcopt(headers):
    """Funzione mantenuta per compatibilità, ma non più utilizzata attivamente."""
    return []

def search_m3u8_in_sites(channel_id, is_tennis=False, session=None):
    """Genera direttamente l'URL di dlhd.dad per il channel_id fornito."""
    return f"https://daddyhd.com/watch.php?id={channel_id}"

def dlhd():
    """
    Estrae canali 24/7 e eventi live da DaddyLive e li salva in un unico file M3U.
    Rimuove automaticamente i canali duplicati.
    """
    print("Eseguendo dlhd...")
    load_dotenv()

    FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
    if FLARESOLVERR_URL:
        FLARESOLVERR_URL = FLARESOLVERR_URL.strip()
    else:
        print("❌ ERRORE: La variabile d'ambiente 'FLARESOLVERR_URL' non è impostata nel file .env. Impossibile continuare.")
        return

    JSON_FILE = "daddyliveSchedule.json"
    OUTPUT_FILE = "dlhd.m3u"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    }

    # ========== FUNZIONI DI SUPPORTO ==========
    def clean_category_name(name):
        return re.sub(r'<[^>]+>', '', name).strip()

    def clean_tvg_id(tvg_id):
        cleaned = re.sub(r'[^a-zA-Z0-9À-ÿ]', '', tvg_id)
        return cleaned.lower()

    # ========== ESTRAZIONE CANALI 24/7 ==========
    print("Estraendo canali 24/7 dalla pagina HTML...")
    html_url = "https://daddyhd.com/24-7-channels.php"
    session = requests.Session()

    try:
        print(f"Accesso a {html_url} con FlareSolverr...")
        payload = {
            "cmd": "request.get",
            "url": html_url,
            "maxTimeout": 120000
        }
        response = requests.post(
            FLARESOLVERR_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=70
        )
        response.raise_for_status()
        result = response.json()

        if result.get("status") != "ok":
            print(f"❌ FlareSolverr fallito per {html_url}: {result.get('message')}")
            raise Exception("FlareSolverr request failed")

        html_content = result["solution"]["response"]
        print("✓ Cloudflare bypassato con FlareSolverr!")
        
        # Parsa l'HTML con BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        cards = soup.find_all('a', class_='card')
        
        print(f"Trovati {len(cards)} canali nella pagina HTML")
 
        channels_247 = []
 
        for card in cards:
            # Estrae il nome del canale
            title_div = card.find('div', class_='card__title')
            if not title_div:
                continue
            
            name = title_div.text.strip()
            
            # Estrae l'ID del canale dall'href
            href = card.get('href', '')
            if not ('id=' in href):
                continue
            
            channel_id = href.split('id=')[1].split('&')[0]
            
            if not name or not channel_id:
                continue

            # Applicazione delle correzioni come prima
            if name == "Sky Calcio 7 (257) Italy":
                name = "DAZN"
            if channel_id == "853":
                name = "Canale 5 Italy"
            
            # Cerca lo stream .m3u8
            stream_url = search_m3u8_in_sites(channel_id, is_tennis="tennis" in name.lower(), session=session)
            
            if stream_url: # La funzione ora restituisce sempre un URL
                channels_247.append((name, stream_url))

        # Conta le occorrenze di ogni nome di canale
        name_counts = {}
        for name, _ in channels_247:
            name_counts[name] = name_counts.get(name, 0) + 1
 
        # Aggiungi un contatore ai nomi duplicati
        final_channels = []
        name_counter = {}
 
        for name, stream_url in channels_247:
            if name_counts[name] > 1:
                if name not in name_counter:
                    # Prima occorrenza di un duplicato, mantieni il nome originale
                    name_counter[name] = 1
                    final_channels.append((name, stream_url))
                else:
                    # Occorrenze successive, aggiungi contatore
                    name_counter[name] += 1
                    new_name = f"{name} ({name_counter[name]})"
                    final_channels.append((new_name, stream_url))
            else:
                final_channels.append((name, stream_url))

        print(f"Trovati {len(channels_247)} canali 24/7")
        channels_247 = final_channels
    except Exception as e:
        print(f"Errore nell'estrazione dei canali 24/7: {e}")
        channels_247 = []

    # ========== ESTRAZIONE EVENTI LIVE ==========
    print("Estraendo eventi live...")
    live_events = []

    if os.path.exists(JSON_FILE):
        try:
            now = datetime.now()
            yesterday_date = (now - timedelta(days=1)).date()

            with open(JSON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            categorized_channels = {}

            for date_key, sections in data.items():
                date_part = date_key.split(" - ")[0]
                try:
                    date_obj = parser.parse(date_part, fuzzy=True).date()
                except Exception as e:
                    print(f"Errore parsing data '{date_part}': {e}")
                    continue

                process_this_date = False
                is_yesterday_early_morning_event_check = False

                if date_obj == now.date():
                    process_this_date = True
                elif date_obj == yesterday_date:
                    process_this_date = True
                    is_yesterday_early_morning_event_check = True
                else:
                    continue

                if not process_this_date:
                    continue

                for category_raw, event_items in sections.items():
                    category = clean_category_name(category_raw)
                    if category.lower() == "tv shows":
                        continue
                    if category not in categorized_channels:
                        categorized_channels[category] = []

                    for item in event_items:
                        time_str = item.get("time", "00:00")
                        event_title = item.get("event", "Evento")

                        try:
                            original_event_time_obj = datetime.strptime(time_str, "%H:%M").time()
                            event_datetime_adjusted_for_display_and_filter = datetime.combine(date_obj, original_event_time_obj)

                            if is_yesterday_early_morning_event_check:
                                start_filter_time = datetime.strptime("00:00", "%H:%M").time()
                                end_filter_time = datetime.strptime("04:00", "%H:%M").time()
                                if not (start_filter_time <= original_event_time_obj <= end_filter_time):
                                    continue
                            else:
                                if now - event_datetime_adjusted_for_display_and_filter > timedelta(hours=2):
                                    continue

                            time_formatted = event_datetime_adjusted_for_display_and_filter.strftime("%H:%M")
                        except Exception as e_time:
                            print(f"Errore parsing orario '{time_str}' per evento '{event_title}' in data '{date_key}': {e_time}")
                            time_formatted = time_str

                        for ch in item.get("channels", []):
                            channel_name = ch.get("channel_name", "")
                            channel_id = ch.get("channel_id", "")

                            tvg_name = f"{event_title} ({time_formatted})"
                            categorized_channels[category].append({
                                "tvg_name": tvg_name,
                                "channel_name": channel_name,
                                "channel_id": channel_id,
                                "event_title": event_title,
                                "category": category
                            })

            # Converti in lista per il file M3U
            for category, channels in categorized_channels.items():
                for ch in channels:
                    try: 
                        # Cerca prima lo stream .m3u8
                        stream = search_m3u8_in_sites(ch["channel_id"], is_tennis="tennis" in ch["channel_name"].lower(), session=session)                        
                        if stream:
                            live_events.append((f"{category} | {ch['tvg_name']}", stream))
                    except Exception as e:
                        print(f"Errore su {ch['tvg_name']}: {e}")

            print(f"Trovati {len(live_events)} eventi live")

        except Exception as e:
            print(f"Errore nell'estrazione degli eventi live: {e}")
            live_events = []
    else:
        print(f"File {JSON_FILE} non trovato, eventi live saltati")

    # ========== GENERAZIONE FILE M3U UNIFICATO ==========
    print("Generando file M3U unificato...")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        # Aggiungi eventi live se presenti
        if live_events:
            f.write(f'#EXTINF:-1 group-title="Live Events",DADDYLIVE\n')
            f.write("https://example.com.m3u8\n\n")

            for name, url in live_events:
                f.write(f'#EXTINF:-1 group-title="Live Events",{name}\n')
                f.write(f'{url}\n\n')

        # Aggiungi canali 24/7
        if channels_247:
            for name, url in channels_247:
                f.write(f'#EXTINF:-1 group-title="DLHD 24/7",{name}\n')
                f.write(f'{url}\n\n')

    total_channels = len(channels_247) + len(live_events)
    print(f"Creato file {OUTPUT_FILE} con {total_channels} canali totali:")
    print(f"  - {len(channels_247)} canali 24/7")
    print(f"  - {len(live_events)} eventi live")

# Funzione per il quarto script (schedule_extractor.py)
def schedule_extractor():
    # Codice del quarto script qui
    # Aggiungi il codice del tuo script "schedule_extractor.py" in questa funzione.
    print("Eseguendo lo schedule_extractor.py...")
    load_dotenv()

    LINK_DADDY = os.getenv("LINK_DADDY", "").strip() or "https://daddyhd.com"
    FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
    if FLARESOLVERR_URL:
        FLARESOLVERR_URL = FLARESOLVERR_URL.strip()
    else:
        print("❌ ERRORE: La variabile d'ambiente 'FLARESOLVERR_URL' non è impostata nel file .env. Impossibile continuare.")
        return

    def html_to_json(html_content):
        """Converte il contenuto HTML della programmazione in formato JSON."""
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {}
        
        schedule_div = soup.find('div', id='schedule')
        if not schedule_div:
            schedule_div = soup.find('div', class_='schedule schedule--compact')
        
        if not schedule_div:
            print("AVVISO: Contenitore 'schedule' non trovato!")
            return {}
        
        day_title_tag = schedule_div.find('div', class_='schedule__dayTitle')
        current_date = day_title_tag.text.strip() if day_title_tag else "Unknown Date"
        
        result[current_date] = {}
        
        for category_div in schedule_div.find_all('div', class_='schedule__category'):
            cat_header = category_div.find('div', class_='schedule__catHeader')
            if not cat_header: continue
            
            cat_meta = cat_header.find('div', class_='card__meta')
            if not cat_meta: continue
            
            current_category = cat_meta.text.strip()
            result[current_date][current_category] = []
            
            category_body = category_div.find('div', class_='schedule__categoryBody')
            if not category_body: continue
            
            for event_div in category_body.find_all('div', class_='schedule__event'):
                event_header = event_div.find('div', class_='schedule__eventHeader')
                if not event_header: continue
                
                time_span = event_header.find('span', class_='schedule__time')
                event_title_span = event_header.find('span', class_='schedule__eventTitle')
                
                event_data = {
                    'time': time_span.text.strip() if time_span else '',
                    'event': event_title_span.text.strip() if event_title_span else 'Evento Sconosciuto',
                    'channels': []
                }
                
                channels_div = event_div.find('div', class_='schedule__channels')
                if channels_div:
                    for link in channels_div.find_all('a', href=True):
                        href = link.get('href', '')
                        channel_id_match = re.search(r'id=(\d+)', href)
                        if channel_id_match:
                            channel_id = channel_id_match.group(1)
                            channel_name = link.get('title', link.text.strip())
                            event_data['channels'].append({
                                'channel_name': channel_name,
                                'channel_id': channel_id
                            })
                
                if event_data['channels']:
                    result[current_date][current_category].append(event_data)
        return result
    
    def modify_json_file(json_file_path):
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"File JSON modificato e salvato in {json_file_path}")
    
    def extract_schedule_container():
        url = f"{LINK_DADDY}/"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_output = os.path.join(script_dir, "daddyliveSchedule.json")
        
        print(f"Accesso a {url} con FlareSolverr...")
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        
        try:
            response = requests.post(FLARESOLVERR_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=70)
            result = response.json()
            
            if result.get("status") != "ok":
                print(f"❌ FlareSolverr fallito: {result.get('message')}")
                return False
            
            html_content = result["solution"]["response"]
            print("✓ Cloudflare bypassato con FlareSolverr!")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            schedule_div = soup.find('div', id='schedule')
            if not schedule_div:
                schedule_div = soup.find('div', class_='schedule schedule--compact')
            
            if not schedule_div:
                print("❌ #schedule non trovato!")
                return False
            
            print("✓ Schedule estratto!")
            json_data = html_to_json(str(schedule_div))
            
            with open(json_output, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=4)
            
            print(f"✓ Salvato in {json_output}")
            modify_json_file(json_output)
            return True
            
        except Exception as e:
            print(f"❌ ERRORE: {str(e)}")
            return False
    
    if __name__ == "__main__":
        success = extract_schedule_container()
        if not success:
            exit(1)

def vavoo_channels():
    # Codice del settimo script qui
    # Aggiungi il codice del tuo script "world_channels_generator.py" in questa funzione.
    print("Eseguendo vavoo_channels...")
    
    def getAuthSignature():
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "content-length": "1106",
            "accept-encoding": "gzip"
        }
        data = {
            "token": "tosFwQCJMS8qrW_AjLoHPQ41646J5dRNha6ZWHnijoYQQQoADQoXYSo7ki7O5-CsgN4CH0uRk6EEoJ0728ar9scCRQW3ZkbfrPfeCXW2VgopSW2FWDqPOoVYIuVPAOnXCZ5g",
            "reason": "app-blur",
            "locale": "de",
            "theme": "dark",
            "metadata": {
                "device": {
                    "type": "Handset",
                    "os": "Android",
                    "osVersion": "10",
                    "model": "Pixel 4",
                    "brand": "Google"
                }
            }
        }
        resp = requests.post("https://vavoo.to/mediahubmx-signature.json", json=data, headers=headers, timeout=10)
        return resp.json().get("signature")
    
    def vavoo_groups():
        # Puoi aggiungere altri gruppi per più canali
        return [""]
    
    def clean_channel_name(name):
        """Rimuove i suffissi .a, .b, .c dal nome del canale"""
        # Rimuove .a, .b, .c alla fine del nome (con o senza spazi prima)
        cleaned_name = re.sub(r'\s*\.(a|b|c|s|d|e|f|g|h|i|j|k|l|m|n|o|p|q|r|t|u|v|w|x|y|z)\s*$', '', name, flags=re.IGNORECASE)
        return cleaned_name.strip()
    
    def get_channels():
        signature = getAuthSignature()
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "accept-encoding": "gzip",
            "mediahubmx-signature": signature
        }
        all_channels = []
        for group in vavoo_groups():
            cursor = 0
            while True:
                data = {
                    "language": "de",
                    "region": "AT",
                    "catalogId": "iptv",
                    "id": "iptv",
                    "adult": False,
                    "search": "",
                    "sort": "name",
                    "filter": {"group": group},
                    "cursor": cursor,
                    "clientVersion": "3.0.2"
                }
                resp = requests.post("https://vavoo.to/mediahubmx-catalog.json", json=data, headers=headers, timeout=10)
                r = resp.json()
                items = r.get("items", [])
                all_channels.extend(items)
                cursor = r.get("nextCursor")
                if not cursor:
                    break
        return all_channels
    
    def save_as_m3u(channels, filename="vavoo.m3u"):
        # 1. Raccogli tutti i canali in una lista flat
        all_channels_flat = []
        for ch in channels:
            original_name = ch.get("name", "SenzaNome")
            name = clean_channel_name(original_name)
            url = ch.get("url", "")
            category = ch.get("group", "Generale")
            if url:
                all_channels_flat.append({'name': name, 'url': url, 'category': category})

        # 2. Conta le occorrenze di ogni nome
        name_counts = {}
        for ch_data in all_channels_flat:
            name_counts[ch_data['name']] = name_counts.get(ch_data['name'], 0) + 1

        # 3. Rinomina i duplicati
        final_channels_data = []
        name_counter = {}
        for ch_data in all_channels_flat:
            name = ch_data['name']
            if name_counts[name] > 1:
                if name not in name_counter:
                    name_counter[name] = 1
                    new_name = name  # Mantieni il nome originale per la prima occorrenza
                else:
                    name_counter[name] += 1
                    new_name = f"{name} ({name_counter[name]})"
            else:
                new_name = name
            final_channels_data.append({'name': new_name, 'url': ch_data['url'], 'category': ch_data['category']})

        # 4. Raggruppa i canali per categoria per la scrittura del file
        channels_by_category = {}
        for ch_data in final_channels_data:
            category = ch_data['category']
            if category not in channels_by_category:
                channels_by_category[category] = []
            channels_by_category[category].append((ch_data['name'], ch_data['url']))

        # 5. Scrivi il file M3U
        with open(filename, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for category in sorted(channels_by_category.keys()):
                channel_list = sorted(channels_by_category[category], key=lambda x: x[0].lower())
                f.write(f"\n# {category.upper()}\n")
                for name, url in channel_list:
                    f.write(f'#EXTINF:-1 group-title="{category} VAVOO",{name}\n{url}\n')

        print(f"Playlist M3U salvata in: {filename}")
        print(f"Canali organizzati in {len(channels_by_category)} categorie:")
        for category, channel_list in channels_by_category.items():
            print(f"  - {category}: {len(channel_list)} canali")
    
    if __name__ == "__main__":
        channels = get_channels()
        print(f"Trovati {len(channels)} canali. Creo la playlist M3U con i link proxy...")
        save_as_m3u(channels) 
        
def sportsonline():
    import requests
    import re
    from bs4 import BeautifulSoup
    import datetime
    
    # URL del file di programmazione
    PROG_URL = "https://sportsonline.sn/prog.txt"
    OUTPUT_FILE = "sportsonline.m3u"  # Definito come costante
    
    def get_channel_languages(lines):
        """
        Analizza le righe del file di programmazione per mappare i canali con le loro lingue.
        Restituisce un dizionario con chiave=channel_id e valore=lingua (es. {'hd7': 'ITALIAN'}).
        """
        channel_language_map = {}
        for line in lines:
            line_stripped = line.strip()
            # Cerca le righe che definiscono la lingua di un canale (formato: "HD7 ITALIAN")
            if line_stripped and not line_stripped.startswith(('http', '|', '#')) and ' ' in line_stripped:
                parts = line_stripped.split(maxsplit=1)
                if len(parts) == 2:
                    channel_id_raw = parts[0].strip()
                    language = parts[1].strip()
                    # Verifica che il primo elemento sia un ID canale (es. HD7, BR1, ecc.)
                    if channel_id_raw and not any(day in channel_id_raw.upper() for day in 
                        ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]):
                        channel_id = channel_id_raw.lower()
                        channel_language_map[channel_id] = language
                        print(f"[INFO] Trovato canale: {channel_id.upper()} - Lingua: {language}")
        return channel_language_map
    
    def extract_channel_from_url(url):
        """
        Estrae l'identificativo del canale dall'URL.
        Es: https://sportzonline.st/channels/hd/hd5.php -> hd5
        """
        match = re.search(r'/([a-z0-9]+)\.php$', url, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None
    
    print("Eseguendo sportsonline...")
    
    # --- Controllo del giorno della settimana ---
    today_weekday = datetime.date.today().weekday()
    weekdays_english = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    day_to_filter = weekdays_english[today_weekday]
    print(f"Oggi è {day_to_filter}, verranno cercati solo gli eventi di oggi.")

    print(f"1. Scarico la programmazione da: {PROG_URL}")
    try:
        response = requests.get(PROG_URL, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERRORE FATALE] Impossibile scaricare il file di programmazione: {e}")
        return

    lines = response.text.splitlines()

    print("\n2. Mappo i canali con le rispettive lingue...")
    channel_language_map = get_channel_languages(lines)

    if not channel_language_map:
        print("[ATTENZIONE] Nessun canale con lingua trovato nella programmazione.")
        return

    playlist_entries = []

    print("\n3. Cerco gli Eventi trasmessi...")

    processing_today_events = False

    for line in lines:
        line_upper = line.upper().strip()

        # Controlliamo se la riga è un'intestazione di un giorno della settimana
        if line_upper in weekdays_english:
            if line_upper == day_to_filter:
                processing_today_events = True
            else:
                processing_today_events = False
            continue

        # Processiamo la riga solo se siamo nella sezione del giorno giusto
        if not processing_today_events:
            continue

        if '|' not in line:
            continue

        parts = line.split('|')
        if len(parts) != 2:
            continue

        event_info = parts[0].strip()
        page_url = parts[1].strip()

        # Estrae il canale dall'URL
        channel_id = extract_channel_from_url(page_url)
        
        if channel_id and channel_id in channel_language_map:
            language = channel_language_map[channel_id]
            print(f"\n[EVENTO] Trovato evento: '{event_info}' - Canale: {channel_id.upper()} - Lingua: {language}")
            
            # Riformattiamo il nome dell'evento: Nome Evento Orario [LINGUA]
            event_parts = event_info.split(maxsplit=1)
            if len(event_parts) == 2:
                time_str_original, name_only = event_parts
                
                # Aggiungi 1 ora all'orario
                try:
                    original_time = datetime.datetime.strptime(time_str_original.strip(), '%H:%M')
                    new_time = original_time + datetime.timedelta(hours=1)
                    time_str = new_time.strftime('%H:%M')
                except ValueError:
                    time_str = time_str_original.strip()
                
                event_name = f"{name_only.strip()} {time_str} [{language}]"
            else:
                event_name = f"{event_info} [{language}]"

            playlist_entries.append({
                "name": event_name,
                "url": page_url,
                "referrer": "https://sportsonline.sn/",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
    
    # Creazione canale fallback se non ci sono eventi
    if not playlist_entries:
        print("\n[INFO] Nessun evento trovato oggi.")
        print("[INFO] Creo un canale fallback 'NESSUN EVENTO'...")
        playlist_entries.append({
            "name": "NESSUN EVENTO", 
            "url": "https://cph-p2p-msl.akamaized.net/hls/live/2000341/test/master.m3u8",
            "referrer": "https://sportsonline.sn/",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    # 4. Creazione del file M3U
    print(f"\n4. Scrivo la playlist nel file: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for entry in playlist_entries:
            f.write(f'#EXTINF:-1 group-title="Live Events SPORTSONLINE",{entry["name"]}\n')
            f.write(f'{entry["url"]}\n')

    print(f"\n[COMPLETATO] Playlist creata con successo! Apri il file '{OUTPUT_FILE}' con un player come VLC.")

def main():
    try:
        try:
            schedule_extractor()
        except Exception as e:
            print(f"Errore durante l'esecuzione di schedule_extractor: {e}")
            return
        try:
            vavoo_channels()
        except Exception as e:
            print(f"Errore durante l'esecuzione di vavoo_channels: {e}")
            return
        try:
            dlhd()
        except Exception as e:
            print(f"Errore durante l'esecuzione di dlhd: {e}")
            return
        try:
            sportsonline()
        except Exception as e:
            print(f"Errore durante l'esecuzione di sportsonline: {e}")
            return
        print("Tutti gli script sono stati eseguiti correttamente!")
    finally:
        pass

if __name__ == "__main__":
    main()
