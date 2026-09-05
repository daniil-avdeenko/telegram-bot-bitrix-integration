from flask import Flask, request, jsonify
import requests
import re
import logging
import os
from dotenv import load_dotenv
#Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
load_dotenv()

#Определяем Телеграм-токен и Битрикс-вебхук
T_token = os.getenv("T_token")
B_webhook = os.getenv("B_webhook")

if not T_token or not B_webhook:
    logging.error("Не загружены переменные окружения, проверьте .env файл.")

#Ф-ция для отправки сообщения в Telegram
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{T_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info(f"Сообщение отправлено в чат {chat_id}")
        else:
            logger.error(f"Ошибка отправки: {response.text}")
    except Exception as e:
        logger.error(f"Исключение при отправке: {e}")


#Создание лида в Битрикс
def create_bitrix_lead(name, phone, comment):

    lead_data = {
        "entityTypeId": 1,
        "fields": {
            "title": f"Заявка из Telegram от {name}",
            "name": name,
            "comments": comment
        }
    }

    #Добавляем номер телефона, если найден
    if phone:
        lead_data["fields"]["fm"] = [
            {
                "typeId": "PHONE",
                "value": phone,
                "valueType": "WORK"
            }
        ]

    url = B_webhook + "crm.item.add"
    logger.info(f"Отправка запроса в Битрикс24: {lead_data}")

    try:
        response = requests.post(url, json=lead_data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if "result" in result and "item" in result["result"]:
                lead_id = result["result"]["item"]["id"]
                logger.info(f"Лид создан, ID: {lead_id}")
                return True, lead_id
            else:
                error_msg = f"Возникла ошибка: {result}"
                logger.error(error_msg)
                return False, error_msg
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        logger.error(f"Исключение при создании лида: {e}")
        return False, str(e)


#Обработчик вебхука
@app.route('/webhook', methods=['POST'])
def webhook():
    #Убеждаемся, что получен JSON
    if not request.is_json:
        logger.warning("Получен запрос не в формате JSON")
        return jsonify({"status": "bad request"}), 400

    data = request.get_json()
    logger.info(f"Получены данные: {data}")

    #Проверяем, что это сообщение
    if 'message' not in data:
        logger.info("Получен не message-запрос")
        return jsonify({"status": "ok"}), 200

    msg = data['message']
    chat_id = msg['chat']['id']
    user_name = msg['chat'].get('first_name', 'Пользователь')
    text = msg.get('text', '')

    logger.info(f"Сообщение от {user_name} (chat_id={chat_id}): {text}")

    #Извлекаем телефон из текста в виде +7 или 8 с 10 цифрами
    phone_match = re.search(r'(\+7|8)\d{10}', text)
    phone = phone_match.group(0) if phone_match else None

    #Создаём лид
    success, result = create_bitrix_lead(user_name, phone, text)

    #Готовим ответ пользователю
    if success:
        reply = f"✅ Спасибо, {user_name}! Ваша заявка принята (ID #{result}). Менеджер свяжется с Вами в ближайшее время."
    else:
        reply = f"❌ Произошла ошибка при создании заявки. Попробуйте позже."
        logger.error(f"Ошибка создания лида: {result}")

    send_telegram_message(chat_id, reply)
    return jsonify({"status": "ok"}), 200

#Запуск сервера
if __name__ == '__main__':
    logger.info("Запуск сервера на http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)