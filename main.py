import requests;    import time
import re;          import sqlite3
import random;      import json
import aiohttp;     import aiosqlite

from lxml           import html
from bs4            import BeautifulSoup
from fake_useragent import UserAgent

from telegram       import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext   import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import asyncio

# =================================================================================================================== #

TELEGRAM_BOT_API_TOKEN  = "7849335572:AAHt8FY95JSlg5uUFhpyHygD-RHQZwRciXo"
db_file                 = "database.db"
parsing                 = False

# =================================================================================================================== #

conn = sqlite3.connect(db_file)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    use_proxy INTEGER DEFAULT 0,
    proxy_ip TEXT DEFAULT NULL,
    proxy_port TEXT DEFAULT NULL,
    proxy_username TEXT DEFAULT NULL,
    proxy_password TEXT DEFAULT NULL,
    apanel_password TEXT DEFAULT "5159"
)
""")

cursor.execute("SELECT COUNT(*) FROM config")
config_entry_count = cursor.fetchone()[0]
if config_entry_count == 0:
    cursor.execute("INSERT INTO config (use_proxy, apanel_password) VALUES (?, ?)", (0, "5159"))
    print("[DATABASE] Таблица 'config' была пуста, вставлена запись по умолчанию, требуется настройка через админ-панель")

conn.commit()
conn.close()

# =================================================================================================================== #

async def generate_headers():
    fake_ua = UserAgent()
    headers = {
        'User-Agent': fake_ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': random.choice(['en-US', 'en-GB', 'ru-RU']),
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'TE': 'Trailers'
    }
    return headers

async def fetch(session, url, params=None, headers=None, proxies=None):
    async with session.get(url, params=params, headers=headers, proxy=proxies) as response:
        response.raise_for_status()
        return await response.text()

# =================================================================================================================== #

async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id, f"Привет, я твой тайный-информатор\n\nМоя задача заключается в том, чтобы позвать тебя, если я найду что-то интересное\n\nДля того чтобы начать заниматься делами необходимо настроить это в панели администрирования")

async def command_apanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- --- --- --- --- --- --- --- --- --- #
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT apanel_password FROM config LIMIT 1")
    current_password = cursor.fetchone()[0]
    cursor.execute("SELECT use_proxy FROM config LIMIT 1")
    is_use_proxy = cursor.fetchone()[0]
    conn.close()
    # --- --- --- --- --- --- --- --- --- --- #
    password = update.message.text.replace('/apanel', '').strip()
    # --- --- --- --- --- --- --- --- --- --- #
    if password != current_password: await update.message.reply_text("Отказано в доступе")
    else:
        context.user_data['is_admin'] = True
        global parsing

        keyboard    = [
            [InlineKeyboardButton("Изменить пароль от панели",  callback_data = "set_new_apanel_password")],
            [InlineKeyboardButton("Подключить прокси" if not is_use_proxy else "Отключить прокси", callback_data = "use_proxy_tumbler")],
            [InlineKeyboardButton("Включить парсинг" if not parsing else "Отключить парсинг", callback_data = "parse_tumbler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Добро пожаловать в панель администрирования\n\nВыберите действие:", reply_markup = reply_markup)
    # --- --- --- --- --- --- --- --- --- --- #

# =================================================================================================================== #

async def go_set_new_apanel_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data['action'] = "set_new_apanel_password"
    await query.message.reply_text("Отправьте новый пароль от панели администрирования")

# =================================================================================================================== #

async def handle_action_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('action')
    if action != None and (not context.user_data.get('is_admin', False)):
        await update.message.reply_text("Отказано в доступе")
        return
    
    if action == "set_new_apanel_password":
        new_apanel_password = update.message.text

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("UPDATE config SET apanel_password = ? WHERE id = (SELECT MAX(id) FROM config)", (new_apanel_password,))
        conn.commit()
        conn.close()

        context.user_data['action'] = None
        await update.message.reply_text("Пароль от панели администрирования успешно обновлен")

    elif action == "typing_proxy_data":
        await update.message.reply_text("Пожалуйста подождите, проверяем работает ли ваш прокси-сервер\n\nОтвет будет в течении 10 секунд...")
        context.user_data['action'] = None

        new_proxy_ip, new_proxy_port, new_proxy_username, new_proxy_password = update.message.text.split(":")
        proxies = {
            "http": f"http://{new_proxy_username}:{new_proxy_password}@{new_proxy_ip}:{new_proxy_port}",
            "https": f"http://{new_proxy_username}:{new_proxy_password}@{new_proxy_ip}:{new_proxy_port}"
        }

        try:
            with requests.get("https://google.com/", proxies = proxies, timeout = 10) as response:
                response.raise_for_status()
                
                conn = sqlite3.connect(db_file)
                cursor = conn.cursor()
                cursor.execute("UPDATE config SET use_proxy = ?, proxy_ip = ?, proxy_port = ?, proxy_username = ?, proxy_password = ? WHERE id = (SELECT MAX(id) FROM config)", (1, new_proxy_ip, new_proxy_port, new_proxy_username, new_proxy_password))
                conn.commit()
                conn.close()

                global parsing
                if parsing:
                    parsing = False

                await update.message.reply_text("Прокси-сервер был успешно привязан к парсеру\n\nЕсли режим парсинга был включен, то возможно его потребуется включить заново")
        except requests.exceptions.RequestException as e:
            await update.message.reply_text("Прокси-сервер не отвечает, попробуйте другой прокси-сервер")

# =================================================================================================================== #
MAX_CONCURRENT_TASKS = 30
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

async def fetch_proxies(conn):
    """
    Извлекает информацию о прокси из базы данных и формирует строку прокси для использования в aiohttp.
    """
    async with conn.execute("SELECT use_proxy FROM config LIMIT 1") as cursor:
        is_use_proxy = (await cursor.fetchone())[0]

    if is_use_proxy == 0:
        # Если прокси не используется, вернуть None
        return None

    async with conn.execute(
        """
        SELECT proxy_ip, proxy_port, proxy_username, proxy_password
        FROM config
        WHERE id = (SELECT MAX(id) FROM config)
        """
    ) as cursor:
        proxy_data = await cursor.fetchone()

    if proxy_data:
        proxy_ip, proxy_port, proxy_username, proxy_password = proxy_data
        return f"http://{proxy_username}:{proxy_password}@{proxy_ip}:{proxy_port}"
    else:
        # Если данных о прокси нет, вернуть None
        return None


async def fetch_asset(session, assetid, proxies, semaphore):
    async with semaphore:
        try:
            parse_url = f"https://www.otherside-wiki.xyz/otherdeed/plot/{assetid}"
            async with session.get(parse_url, proxy=proxies) as response:
                response.raise_for_status()
                page_content = await response.text()
                tree = html.fromstring(page_content)

                fair_value_xpath = '/html/body/div[3]/div/div[2]/div[1]/a[1]/div/div[2]'
                fair_value_element = tree.xpath(fair_value_xpath)

                if not fair_value_element:
                    print(f"[PARSE] Элемент для получения значения Fair Value не был найден | NFT URL: {parse_url}")
                    return None

                fair_value = fair_value_element[0].text.strip()
                match = re.search(r'(\d+\.\d+|\d+)', fair_value)
                if match:
                    fair_value = match.group(0)
                else:
                    print(f"[PARSE] Ошибка обработки переменных | Код ошибки 43 | NFT URL: {parse_url}")
                    return None

                buy_value_elements = [
                    tree.xpath(f"/html/body/div[3]/div/div[2]/div[1]/a[{i}]/div/div[2]")
                    for i in range(4, 8)
                ]
                buy_values = [
                    float(re.search(r'(\d+\.\d+|\d+)', el[0].text.strip()).group(0))
                    for el in buy_value_elements if el
                ]

                if not buy_values:
                    print(f"[PARSE] Нет действительных buy_value для актива #{assetid}")
                    return None

                favorite_buy_value = min(buy_values)
                result = float(fair_value) / favorite_buy_value

                return {
                    "assetid": assetid,
                    "fair_value": fair_value,
                    "buy_value": favorite_buy_value,
                    "result": result,
                    "url": parse_url
                }
        except Exception as e:
            print(f"[PARSE] Ошибка при запросе актива #{assetid}: {e}")
            return None


async def run_parsing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    global parsing
    await query.message.reply_text("Пожалуйста, подождите, включаем режим парсинга...")

    async with aiosqlite.connect(db_file) as conn:
        proxies = await fetch_proxies(conn)

    browse_nft_url = "https://www.otherside-wiki.xyz/api/browse_otherdeeds.php"
    params = {
        "type": "Items",
        "page": 1,
        "quicksearch": "",
        "price_range_downlimit": "",
        "price_range_uplimit": "",
        "grailscore": "",
        "range_resource_rarity": "",
        "otherdeedid": "",
        "id_range_downlimit": "",
        "id_range_uplimit": "",
        "lotm_fragments_downlimit": "",
        "lotm_fragments_uplimit": "",
        "sortBy": "pricelowtohigh",
    }

    sem = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    async with aiohttp.ClientSession() as session:
        while parsing:
            await asyncio.sleep(0)

            try:
                headers = await generate_headers()
                async with session.get(browse_nft_url, params=params, headers=headers, proxy=proxies) as response:
                    response.raise_for_status()
                    clearesponse = await response.text()
                    clearesponse = clearesponse.lstrip('\ufeff')  # Удаляем BOM
                    data = json.loads(clearesponse)
                    total_pages = int(data['meta']['totalPages'])
            except Exception as e:
                parsing = False
                await query.message.reply_text(f"Произошла ошибка\n\nКод 217\n\nException as '{e}'")
                break

            assets_ids = []
            for page in range(1, total_pages + 1):
                params["page"] = page
                try:
                    headers = await generate_headers()
                    async with session.get(browse_nft_url, params=params, headers=headers, proxy=proxies) as response:
                        response.raise_for_status()
                        clearesponse = await response.text()
                        clearesponse = clearesponse.lstrip('\ufeff')  # Удаляем BOM
                        data = json.loads(clearesponse)
                        for item in data["data"]:
                            if "assetid" in item:
                                assets_ids.append(int(item["assetid"]))
                except Exception as e:
                    parsing = False
                    await query.message.reply_text(f"Произошла ошибка\n\nКод 218\n\nException as '{e}'")
                    break

            print(f"[PARSE] Было найдено {len(assets_ids)} предложений, начинаем анализ ценового сегмента и разниц")

            async def process_asset(assetid):
                async with sem:
                    try:
                        parse_url = f"https://www.otherside-wiki.xyz/otherdeed/plot/{assetid}"
                        async with session.get(parse_url, proxy=proxies) as response:
                            response.raise_for_status()
                            page_content = await response.text()
                            tree = html.fromstring(page_content)
                            fair_value_xpath = "/html/body/div[3]/div/div[2]/div[1]/a[1]/div/div[2]"
                            fair_value_element = tree.xpath(fair_value_xpath)

                            if not fair_value_element:
                                print(f"[PARSE] Элемент для получения значения Fair Value не был найден | NFT URL: {parse_url}")
                                return

                            fair_value = fair_value_element[0].text.strip()
                            match = re.search(r"(\d+\.\d+|\d+)", fair_value)
                            if match:
                                fair_value = match.group(0)
                            else:
                                print(f"[PARSE] Ошибка обработки переменных | Код ошибки 43 | NFT URL: {parse_url}")
                                return

                            if "No active listings" in tree.text_content():
                                print(f"[INFO] Актив #{assetid} имеет Fair Value {fair_value} ETH, но активных предложений нет | NFT URL: {parse_url}")
                                return

                            buy_value_elements = [
                                tree.xpath("/html/body/div[3]/div/div[2]/div[1]/a[4]/div/div[2]"),
                                tree.xpath("/html/body/div[3]/div/div[2]/div[1]/a[5]/div/div[2]"),
                                tree.xpath("/html/body/div[3]/div/div[2]/div[1]/a[6]/div/div[2]"),
                                tree.xpath("/html/body/div[3]/div/div[2]/div[1]/a[7]/div/div[2]"),
                            ]

                            buy_values = []
                            for i, element in enumerate(buy_value_elements, start=1):
                                if element:
                                    try:
                                        value_text = element[0].text.strip()
                                        match = re.search(r"(\d+\.\d+|\d+)", value_text)
                                        if match:
                                            buy_values.append(float(match.group(0)))
                                        else:
                                            print(f"[PARSE] Ошибка извлечения числа из элемента {i} | Код ошибки 52 | NFT URL: {parse_url}")
                                    except Exception as e:
                                        print(f"[PARSE] Не удалось обработать элемент {i}: {e} | Код ошибки 53 | NFT URL: {parse_url}")

                            if buy_values:
                                favorite_buy_value = min(buy_values)
                            else:
                                print(f"[PARSE] Не удалось найти действительных значений для buy_value | Код ошибки 55 | NFT URL: {parse_url}")
                                return

                            result = float(fair_value) / float(favorite_buy_value)
                            if result < 1.7:
                                print(
                                    f"[PARSE] Коэфициент между справедливой и рыночной стоимостью составил - {result} | NFT URL: {parse_url} | Fair Value: {fair_value} ETH | Buy Value: {favorite_buy_value} ETH"
                                )
                            else:
                                print(
                                    f"[PARSE-GODSEND] Коэфициент между справедливой и рыночной стоимостью составил - {result} | NFT URL: {parse_url} | Fair Value: {fair_value} ETH | Buy Value: {favorite_buy_value} ETH"
                                )
                                await query.message.reply_text(
                                    f"Нашёл кое-что интересное\n\n"
                                    f"Найден NFT с коэффициентом {result}\n\n"
                                    f"Ссылка: {parse_url}\n\n"
                                    f"Fair Value: {fair_value} ETH\nBuy Value: {favorite_buy_value} ETH"
                                )
                    except Exception as e:
                        print(f"[PARSE] Ошибка при запросе страницы | NFT URL: {parse_url} | Exception: {e}")

            # Обрабатываем все assets_ids через семафор
            tasks = [process_asset(assetid) for assetid in assets_ids]
            await asyncio.gather(*tasks)

    await query.message.reply_text("Парсинг успешно остановлен")


async def parse_tumbler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Включает или отключает режим парсинга.
    """
    query = update.callback_query
    await query.answer()

    global parsing
    if parsing:
        # Если парсинг уже запущен, останавливаем его
        parsing = False
        await query.message.reply_text(
            "Пожалуйста, подождите. Останавливаем парсинг, это может занять немного времени..."
        )
    else:
        # Если парсинг не запущен, активируем его
        parsing = True
        await query.message.reply_text(
            "Режим парсинга включен. Начинаем сканирование рынка.\n\n"
            "Вы можете отдохнуть — бот уведомит вас, если найдёт что-то интересное."
        )
        print("[PARSE] Режим парсинга активирован.")
        
        # Запускаем процесс парсинга в отдельной асинхронной задаче
        asyncio.create_task(run_parsing(update, context))



async def proxy_tumbler_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not context.user_data.get('is_admin', False):
        await query.message.reply_text("Отказано в доступе")
        return
    
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT use_proxy FROM config LIMIT 1")
    is_use_proxy = cursor.fetchone()[0]

    if is_use_proxy != 0:
        cursor.execute("UPDATE config SET use_proxy = ?, proxy_ip = NULL, proxy_port = NULL, proxy_username = NULL, proxy_password = NULL WHERE id = (SELECT MAX(id) FROM config)", (0,))
        global parsing
        if parsing:
            parsing = False
        await query.message.reply_text("Вы успешно отключили использование прокси для соединения\n\nЕсли при выполнении этого действия был включен режим парсинга, то необходимо заново запустить режим парсинга")
    else:
        context.user_data['action'] = "typing_proxy_data"
        await query.message.reply_text("Отправьте данные от прокси-сервер в поддерживаемом формате\n\nПример сообщения, которое вам нужно отправить в ответ на это сообщение:\n\n'proxy_ip:proxy_port:proxy_username:proxy_password'\n'192.168.0.1:8000:myuser:mypass'")

    conn.commit()
    conn.close()

# =================================================================================================================== #

def main():
    application = Application.builder().token(TELEGRAM_BOT_API_TOKEN).build()

    application.add_handler(CommandHandler("start", command_start))
    application.add_handler(CommandHandler("apanel", command_apanel))

    application.add_handler(CallbackQueryHandler(go_set_new_apanel_password,    pattern = "set_new_apanel_password"))
    application.add_handler(CallbackQueryHandler(proxy_tumbler_callback,        pattern = "use_proxy_tumbler"))
    application.add_handler(CallbackQueryHandler(parse_tumbler_callback,        pattern = "parse_tumbler"))

    application.add_handler(MessageHandler(filters.TEXT, handle_action_events))

    application.run_polling()

if __name__ == "__main__":
    main()