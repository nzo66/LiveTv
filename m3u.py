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
except ImportError:
    print("ERROR: Missing required libraries. Please run: pip install requests beautifulsoup4 python-dateutil playwright", file=sys.stderr)

# Disabilita gli avvisi di sicurezza per le richieste senza verifica SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dlhd():
    """
    Estrae canali 24/7 e eventi live da DaddyLive e li salva in un unico file M3U.
    Rimuove automaticamente i canali duplicati.
    """
    print("Eseguendo dlhd...")

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

    def get_stream_from_channel_id(channel_id):
        return f"https://dlhd.dad/watch.php?id={channel_id}"

    # ========== ESTRAZIONE CANALI 24/7 ==========
    print("Estraendo canali 24/7...")
    json_url = "https://dlhd.dad/daddy.json"

    try:
        response = requests.get(json_url, headers=HEADERS, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
 
        channels_247 = []
 
        for channel in data:
            name = channel.get("channel_name")
            channel_id = channel.get("channel_id")
            if not name or not channel_id:
                continue
 
            if name == "Sky Calcio 7 (257) Italy":
                name = "DAZN"
            if channel_id == "853":
                name = "Canale 5 Italy"
            stream_url = f"https://dlhd.dad/watch.php?id={channel_id}"
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

        channels_247.sort(key=lambda x: x[0].lower())
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
                        stream = get_stream_from_channel_id(ch["channel_id"])
                        if stream:
                            live_events.append((f"{category} | {ch['tvg_name']} | {ch['channel_name']}", stream))
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
                f.write(f'#EXTINF:-1 group-title="Live Events",{name}\n{url}\n\n')

        # Aggiungi canali 24/7
        if channels_247:
            for name, url in channels_247:
                f.write(f'#EXTINF:-1 group-title="DLHD 24/7",{name}\n{url}\n\n')

    total_channels = len(channels_247) + len(live_events)
    print(f"Creato file {OUTPUT_FILE} con {total_channels} canali totali:")
    print(f"  - {len(channels_247)} canali 24/7")
    print(f"  - {len(live_events)} eventi live")

# Funzione per il quarto script (schedule_extractor.py)
def schedule_extractor():
    # Codice del quarto script qui
    # Aggiungi il codice del tuo script "schedule_extractor.py" in questa funzione.
    print("Eseguendo lo schedule_extractor.py...")

    def html_to_json(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        result = {}

        schedule_days = soup.find_all('div', class_='schedule__day')
        if not schedule_days:
            print("AVVISO: Nessun 'schedule__day' trovato nel contenuto HTML!")
            return {}

        for day_div in schedule_days:
            day_title_div = day_div.find('div', class_='schedule__dayTitle')
            if not day_title_div:
                continue
            current_date = day_title_div.get_text(strip=True)
            result[current_date] = {}

            for category_div in day_div.find_all('div', class_='schedule__category'):
                cat_header = category_div.find('div', class_='schedule__catHeader')
                if not cat_header:
                    continue
                
                # Usiamo l'HTML interno per mantenere eventuali tag, come in precedenza
                current_category_html = cat_header.find('div', class_='card__meta').decode_contents()
                current_category = current_category_html.strip() + "</span>" # Mantiene la compatibilità con il formato precedente
                result[current_date][current_category] = []

                for event_div in category_div.find_all('div', class_='schedule__event'):
                    event_header = event_div.find('div', class_='schedule__eventHeader')
                    if not event_header:
                        continue

                    time_span = event_header.find('span', class_='schedule__time')
                    event_title_span = event_header.find('span', class_='schedule__eventTitle')

                    event_time = time_span.get_text(strip=True) if time_span else ""
                    event_info = event_title_span.get_text(strip=True) if event_title_span else ""

                    event_data = {
                        "time": event_time,
                        "event": event_info,
                        "channels": []
                    }

                    channels_div = event_div.find('div', class_='schedule__channels')
                    if channels_div:
                        for link in channels_div.find_all('a'):
                            href = link.get('href', '')
                            channel_id_match = re.search(r'(?:watch|stream)-(\d+)\.php', href) or re.search(r'id=(\d+)', href)
                            if channel_id_match:
                                channel_id = channel_id_match.group(1)
                                channel_name = link.get_text(strip=True)
                                event_data["channels"].append({
                                    "channel_name": channel_name,
                                    "channel_id": channel_id
                                })
                    result[current_date][current_category].append(event_data)
        return result
    
    def modify_json_file(json_file_path):
        with open(json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        current_month = datetime.now().strftime("%B")
    
        for date in list(data.keys()):
            match = re.match(r"(\w+\s\d+)(st|nd|rd|th)\s(\d{4})", date)
            if match:
                day_part = match.group(1)
                suffix = match.group(2)
                year_part = match.group(3)
                new_date = f"{day_part}{suffix} {current_month} {year_part}"
                data[new_date] = data.pop(date)
    
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        print(f"File JSON modificato e salvato in {json_file_path}")
    
    def extract_schedule_container():
        url = f"https://dlhd.dad/"

        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_output = os.path.join(script_dir, "daddyliveSchedule.json")

        print(f"Accesso alla pagina {url} per estrarre il contenitore della programmazione...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
    
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Tentativo {attempt} di {max_attempts}...")
                    page.goto(url)
                    print("Attesa per il caricamento completo...")
                    page.wait_for_timeout(10000)  # 10 secondi

                    schedule_content = page.evaluate("""() => {
                        const container = document.querySelector('body');
                        return container ? container.outerHTML : '';
                    }""")

                    if not schedule_content:
                        print("AVVISO: Contenuto della pagina non trovato o vuoto!")
                        if attempt == max_attempts:
                            browser.close()
                            return False
                        else:
                            continue
    
                    print("Conversione HTML della programmazione principale in formato JSON...")
                    json_data = html_to_json(schedule_content)
    
                    with open(json_output, "w", encoding="utf-8") as f:
                        json.dump(json_data, f, indent=4)
    
                    print(f"Dati JSON salvati in {json_output}")
    
                    modify_json_file(json_output)
                    browser.close()
                    return True
    
                except Exception as e:
                    print(f"ERRORE nel tentativo {attempt}: {str(e)}")
                    if attempt == max_attempts:
                        print("Tutti i tentativi falliti!")
                        browser.close()
                        return False
                    else:
                        print(f"Riprovando... (tentativo {attempt + 1} di {max_attempts})")
    
            browser.close()
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
        print("Tutti gli script sono stati eseguiti correttamente!")
    finally:
        pass

if __name__ == "__main__":
    main()
